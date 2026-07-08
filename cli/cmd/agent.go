package cmd

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/spf13/cobra"
)

var agentCmd = &cobra.Command{
	Use:   "agent",
	Short: "Manage Hermes agents (proxy, romi, ergo)",
}

var agentRunCmd = &cobra.Command{
	Use:   "run [name]",
	Short: "Start an agent daemon",
	Long:  `Start a Hermes agent daemon. Agents: proxy, romi, ergo.`,
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		name := "proxy"
		if len(args) > 0 {
			name = args[0]
		}
		model, _ := cmd.Flags().GetString("model")

		projectDir := findProjectRoot()
		script := filepath.Join(projectDir, "agents", "run_agent.sh")
		if _, err := os.Stat(script); os.IsNotExist(err) {
			fmt.Printf("Agent script not found: %s\n", script)
			return
		}

		agentCmd := exec.Command("/bin/bash", script, name)
		if model != "" {
			agentCmd = exec.Command("/bin/bash", script, name, "--model", model)
		}
		agentCmd.Stdout = os.Stdout
		agentCmd.Stderr = os.Stderr
		if err := agentCmd.Run(); err != nil {
			fmt.Printf("Failed to start agent '%s': %v\n", name, err)
		}
	},
}

var agentStatusCmd = &cobra.Command{
	Use:   "status",
	Short: "Show agent daemon status",
	Run: func(cmd *cobra.Command, args []string) {
		projectDir := findProjectRoot()

		for _, name := range []string{"proxy", "romi", "ergo"} {
			pidFile := filepath.Join(projectDir, "agents", fmt.Sprintf(".%s.pid", name))
			pidBytes, err := os.ReadFile(pidFile)
			if err != nil {
				fmt.Printf("✗ %-8s stopped\n", name)
				continue
			}
			pid := strings.TrimSpace(string(pidBytes))
			if isRunning(pid) {
				logFile := filepath.Join(projectDir, "logs", fmt.Sprintf("%s.log", name))
				fmt.Printf("✓ %-8s running (PID %s)\n", name, pid)
				fmt.Printf("  Log: %s\n", logFile)
			} else {
				fmt.Printf("✗ %-8s stopped (stale PID %s)\n", name, pid)
				os.Remove(pidFile)
			}
		}

		if isRunningByName("staragent") {
			fmt.Printf("✓ %-8s running\n", "staragent")
		} else {
			fmt.Printf("✗ %-8s stopped\n", "staragent")
		}
	},
}

var agentStopCmd = &cobra.Command{
	Use:   "stop",
	Short: "Stop all agent daemons",
	Run: func(cmd *cobra.Command, args []string) {
		projectDir := findProjectRoot()
		script := filepath.Join(projectDir, "agents", "run_agent.sh")

		agentCmd := exec.Command("/bin/bash", script, "stop")
		agentCmd.Stdout = os.Stdout
		agentCmd.Stderr = os.Stderr
		if err := agentCmd.Run(); err != nil {
			fmt.Printf("Failed to stop agents: %v\n", err)
		}
	},
}

var agentSendCmd = &cobra.Command{
	Use:   "send <agent> <command>",
	Short: "Send a command to an agent via NATS",
	Args:  cobra.ExactArgs(2),
	Run: func(cmd *cobra.Command, args []string) {
		name := args[0]
		command := args[1]
		payload, _ := cmd.Flags().GetString("payload")

		nc, err := nats.Connect("127.0.0.1:4222", nats.Timeout(3*time.Second))
		if err != nil {
			fmt.Printf("NATS connection failed: %v\n", err)
			return
		}
		defer nc.Close()

		subject := fmt.Sprintf("starship.agent.%s.command.%s", name, strings.ReplaceAll(command, " ", "."))
		msg := fmt.Sprintf(`{"command":"%s","args":%s}`, command, payload)

		if err := nc.Publish(subject, []byte(msg)); err != nil {
			fmt.Printf("Publish failed: %v\n", err)
			return
		}
		fmt.Printf("Sent command '%s' to agent '%s' on %s\n", command, name, subject)
	},
}

func findProjectRoot() string {
	dir, _ := os.Getwd()
	for {
		if _, err := os.Stat(filepath.Join(dir, "agents")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return dir
		}
		dir = parent
	}
}

func isRunning(pidStr string) bool {
	pid := strings.TrimSpace(pidStr)
	if pid == "" {
		return false
	}
	i, err := strconv.Atoi(pid)
	if err != nil || i <= 0 {
		return false
	}
	return syscall.Kill(i, syscall.Signal(0)) == nil
}

func isRunningByName(name string) bool {
	cmd := exec.Command("pgrep", "-x", name)
	return cmd.Run() == nil
}

func init() {
	agentRunCmd.Flags().StringP("model", "m", "", "Override model (e.g. qwen2.5:7b)")
	agentSendCmd.Flags().StringP("payload", "p", "{}", "JSON payload arguments")
	agentCmd.AddCommand(agentRunCmd)
	agentCmd.AddCommand(agentStatusCmd)
	agentCmd.AddCommand(agentStopCmd)
	agentCmd.AddCommand(agentSendCmd)
	rootCmd.AddCommand(agentCmd)
}
