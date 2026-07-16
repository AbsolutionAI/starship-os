use serde::Deserialize;
use std::path::Path;

#[derive(Debug, Deserialize, Clone)]
pub struct Config {
    pub nats: NatsConfig,
    pub telemetry: TelemetryConfig,
    pub osquery: Option<OsqueryConfig>,
    pub commands: CommandsConfig,
    pub hostname: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
pub struct NatsConfig {
    #[serde(default = "default_nats_url")]
    pub url: String,
    pub token: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
pub struct TelemetryConfig {
    #[serde(default = "default_interval")]
    pub interval_secs: u64,
}

#[derive(Debug, Deserialize, Clone)]
pub struct OsqueryConfig {
    #[serde(default = "default_osquery_binary")]
    pub binary: String,
    #[serde(default = "default_osquery_config")]
    pub config_path: String,
    #[serde(default = "default_osquery_log")]
    pub result_log: String,
}

#[derive(Debug, Deserialize, Clone)]
pub struct CommandsConfig {
    #[serde(default = "default_subscribe")]
    pub subscribe: Vec<String>,
}

fn default_nats_url() -> String {
    "nats://127.0.0.1:4222".to_string()
}

fn default_interval() -> u64 {
    10
}

fn default_osquery_binary() -> String {
    "/opt/starship/bin/osqueryd".to_string()
}

fn default_osquery_config() -> String {
    "/etc/starship/osquery/starshipd.conf".to_string()
}

fn default_osquery_log() -> String {
    "/var/log/starship/osquery_results.jsonl".to_string()
}

fn default_subscribe() -> Vec<String> {
    vec![
        "starship.agent.staragent.command.>".to_string(),
        "agnetic.agent.staragent.command.>".to_string(),
    ]
}

impl Config {
    pub fn load(path: &Path) -> Result<Self, Box<dyn std::error::Error>> {
        let content = std::fs::read_to_string(path)
            .map_err(|e| format!("Failed to read config {}: {}", path.display(), e))?;
        let config: Config = serde_yaml::from_str(&content)
            .map_err(|e| format!("Failed to parse config {}: {}", path.display(), e))?;
        Ok(config)
    }

    pub fn load_from_str(yaml: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let config: Config = serde_yaml::from_str(yaml)?;
        Ok(config)
    }

    pub fn hostname(&self) -> String {
        self.hostname
            .clone()
            .unwrap_or_else(|| std::env::var("STARSHIP_NODE_ID").unwrap_or_else(|_| {
                gethostname::gethostname().to_string_lossy().to_string()
            }))
    }
}
