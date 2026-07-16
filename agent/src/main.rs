mod config;

use config::Config;
use futures_util::StreamExt;
use serde::Serialize;
use std::path::Path;
use std::sync::Arc;
use sysinfo::{Disks, Networks, System};
use tokio::sync::watch;
use tokio::time::{interval, Duration};

#[derive(Serialize, Clone)]
struct Telemetry {
    cpu: f32,
    memory_used: u64,
    memory_total: u64,
    disk_used: u64,
    disk_total: u64,
    rx_bytes: u64,
    tx_bytes: u64,
    timestamp: u64,
    hostname: String,
}

#[derive(Serialize)]
struct CommandResponse {
    status: String,
    message: String,
    timestamp: u64,
    hostname: String,
}

const DEFAULT_CONFIG_PATH: &str = "/etc/starship/agents/staragent.yaml";

fn resolve_config_path() -> Box<Path> {
    if let Ok(p) = std::env::var("STARAGENT_CONFIG") {
        if !p.is_empty() {
            return Path::new(&p).into();
        }
    }
    if let Ok(root) = std::env::var("STARSHIP_ROOT") {
        let p = Path::new(&root).join("etc/starship/agents/staragent.yaml");
        if p.exists() {
            return p.into();
        }
        let p2 = Path::new(&root).join("config/staragent.yaml");
        if p2.exists() {
            return p2.into();
        }
    }
    for rel in &["agent/staragent.yaml", "config/staragent.yaml", "staragent.yaml"] {
        let p = Path::new(rel);
        if p.exists() {
            return p.into();
        }
    }
    Path::new(DEFAULT_CONFIG_PATH).into()
}

fn build_nats_url(cfg: &config::NatsConfig) -> String {
    if let Some(token) = &cfg.token {
        if !token.is_empty() {
            let rest = cfg.url.trim_start_matches("nats://");
            if rest.contains('@') {
                return cfg.url.clone();
            }
            return format!("nats://:{}@{}", token, rest);
        }
    }
    cfg.url.clone()
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cfg_path = resolve_config_path();
    let config = if cfg_path.exists() {
        Config::load(&cfg_path)?
    } else {
        eprintln!("Config not found at {}, using defaults", cfg_path.display());
        Config::load_from_str("{}")?
    };

    let hostname = config.hostname();
    let nats_url = build_nats_url(&config.nats);

    println!("staragent starting — hostname={} nats={}", hostname, nats_url);

    let nc = Arc::new(async_nats::connect(&nats_url).await?);
    println!("Connected to NATS");

    let (shutdown_tx, shutdown_rx) = watch::channel(false);

    // ─── Telemetry loop ───────────────────────────────────────────
    let tel_nc = Arc::clone(&nc);
    let tel_hostname = hostname.clone();
    let tel_interval = config.telemetry.interval_secs;
    let mut tel_rx = shutdown_rx.clone();

    let tel_handle = tokio::spawn(async move {
        let mut sys = System::new();
        let mut ticker = interval(Duration::from_secs(tel_interval));
        let mut prev_rx: u64 = 0;
        let mut prev_tx: u64 = 0;

        loop {
            tokio::select! {
                _ = ticker.tick() => {}
                _ = tel_rx.changed() => {
                    println!("telemetry loop shutting down");
                    break;
                }
            }

            sys.refresh_cpu_all();
            sys.refresh_memory();

            let cpu = sys.global_cpu_usage();
            let memory_used = sys.used_memory();
            let memory_total = sys.total_memory();

            let disks = Disks::new_with_refreshed_list();
            let disk_total: u64 = disks.iter().map(|d| d.total_space()).sum();
            let disk_used: u64 = disks.iter().map(|d| d.total_space() - d.available_space()).sum();

            let networks = Networks::new_with_refreshed_list();
            let (rx, tx): (u64, u64) = networks
                .iter()
                .fold((0, 0), |(r, t), (_, n)| (r + n.received(), t + n.transmitted()));

            let rx_delta = if prev_rx > 0 { rx - prev_rx } else { 0 };
            let tx_delta = if prev_tx > 0 { tx - prev_tx } else { 0 };
            prev_rx = rx;
            prev_tx = tx;

            let ts = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs();

            let telemetry = Telemetry {
                cpu,
                memory_used,
                memory_total,
                disk_used,
                disk_total,
                rx_bytes: rx_delta,
                tx_bytes: tx_delta,
                timestamp: ts,
                hostname: tel_hostname.clone(),
            };

            let payload = serde_json::to_vec(&telemetry).unwrap_or_default();
            let subjects = vec![
                format!("starship.telemetry.{}.status", tel_hostname),
                format!("agnetic.telemetry.{}.status", tel_hostname),
            ];
            for subject in &subjects {
                let b: bytes::Bytes = payload.clone().into();
                if let Err(e) = tel_nc.publish(subject.clone(), b).await {
                    eprintln!("publish error on {}: {}", subject, e);
                }
            }
            if let Err(e) = tel_nc.flush().await {
                eprintln!("flush error: {}", e);
            }
        }
    });

    // ─── Command handler ──────────────────────────────────────────
    let cmd_nc = Arc::clone(&nc);
    let cmd_hostname = hostname.clone();
    let cmd_rx = shutdown_rx.clone();
    let subjects = config.commands.subscribe.clone();

    let cmd_handle = tokio::spawn(async move {
        let mut subscriber_handles = Vec::new();

        for subj in &subjects {
            let nc = Arc::clone(&cmd_nc);
            let host = cmd_hostname.clone();
            let mut rx = cmd_rx.clone();
            let s = subj.clone();

            let handle = tokio::spawn(async move {
                let mut sub = match nc.subscribe(s.clone()).await {
                    Ok(sub) => {
                        println!("Subscribed to {}", s);
                        sub
                    }
                    Err(e) => {
                        eprintln!("Failed to subscribe to {}: {}", s, e);
                        return;
                    }
                };

                loop {
                    tokio::select! {
                        _ = rx.changed() => {
                            break;
                        }
                        msg = sub.next() => {
                            match msg {
                                Some(m) => handle_command(&nc, &m, &host).await,
                                None => break,
                            }
                        }
                    }
                }
            });

            subscriber_handles.push(handle);
        }

        for h in subscriber_handles {
            let _ = h.await;
        }
    });

    // ─── Wait for shutdown ────────────────────────────────────────
    tokio::signal::ctrl_c().await?;
    println!("\nShutting down...");
    let _ = shutdown_tx.send(true);

    let _ = tokio::join!(tel_handle, cmd_handle);
    println!("staragent stopped");
    Ok(())
}

async fn handle_command(nc: &async_nats::Client, msg: &async_nats::Message, hostname: &str) {
    let subject = msg.subject.as_str();
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs();

    let command = subject
        .rsplit('.')
        .next()
        .unwrap_or("unknown")
        .to_string();

    let response = match command.as_str() {
        "ping" | "status" => CommandResponse {
            status: "ok".to_string(),
            message: format!("staragent online on {}", hostname),
            timestamp: ts,
            hostname: hostname.to_string(),
        },
        "reload" | "update_config" => CommandResponse {
            status: "acknowledged".to_string(),
            message: "config reload requested (restart to apply)".to_string(),
            timestamp: ts,
            hostname: hostname.to_string(),
        },
        _ => CommandResponse {
            status: "unknown".to_string(),
            message: format!("unknown command: {}", command),
            timestamp: ts,
            hostname: hostname.to_string(),
        },
    };

    if let Ok(payload) = serde_json::to_vec(&response) {
        let reply_subject = format!("starship.agent.staragent.response.{}", hostname);
        let b: bytes::Bytes = payload.clone().into();
        let _ = nc.publish(reply_subject, b).await;

        if let Some(reply) = &msg.reply {
            let b2: bytes::Bytes = payload.into();
            let _ = nc.publish(reply.to_string(), b2).await;
        }
        let _ = nc.flush().await;
    }
}
