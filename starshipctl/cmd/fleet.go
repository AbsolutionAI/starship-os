package cmd

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
)

func findFleetPy() string {
	// Prefer repo-relative, then installed path
	candidates := []string{}
	if root := findProjectRoot(); root != "" {
		candidates = append(candidates, filepath.Join(root, "services", "fleet.py"))
	}
	candidates = append(candidates,
		"/opt/starship/lib/starship/services/fleet.py",
		"/opt/starship/lib/services/fleet.py",
	)
	for _, c := range candidates {
		if st, err := os.Stat(c); err == nil && !st.IsDir() {
			return c
		}
	}
	return ""
}

func runFleet(args ...string) error {
	script := findFleetPy()
	if script == "" {
		return fmt.Errorf("fleet.py not found (services/fleet.py)")
	}
	cmd := exec.Command("python3", append([]string{script}, args...)...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Env = os.Environ()
	return cmd.Run()
}

var fleetCmd = &cobra.Command{
	Use:   "fleet",
	Short: "Fleet / plant / ops manager commands",
	Long:  "Manage multi-plant fleet topology, ops manager, and red/blue exercises",
}

var fleetStatusCmd = &cobra.Command{
	Use:   "status",
	Short: "Show fleet overview",
	Run: func(cmd *cobra.Command, args []string) {
		if err := runFleet("status"); err != nil {
			fmt.Println(err)
			os.Exit(1)
		}
	},
}

var fleetPlantsCmd = &cobra.Command{
	Use:   "plants",
	Short: "List plants",
	Run: func(cmd *cobra.Command, args []string) {
		if err := runFleet("plants"); err != nil {
			fmt.Println(err)
			os.Exit(1)
		}
	},
}

var fleetNodesCmd = &cobra.Command{
	Use:   "nodes",
	Short: "List known fleet nodes",
	Run: func(cmd *cobra.Command, args []string) {
		if err := runFleet("nodes"); err != nil {
			fmt.Println(err)
			os.Exit(1)
		}
	},
}

var fleetRegisterCmd = &cobra.Command{
	Use:   "register",
	Short: "Register this node in the fleet",
	Run: func(cmd *cobra.Command, args []string) {
		if err := runFleet("register"); err != nil {
			fmt.Println(err)
			os.Exit(1)
		}
	},
}

var fleetExerciseCmd = &cobra.Command{
	Use:   "exercise [start|stop|status]",
	Short: "Control red/blue exercise mode",
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		action := "status"
		if len(args) > 0 {
			action = strings.ToLower(args[0])
		}
		if err := runFleet("exercise", action); err != nil {
			fmt.Println(err)
			os.Exit(1)
		}
	},
}

func init() {
	rootCmd.AddCommand(fleetCmd)
	fleetCmd.AddCommand(fleetStatusCmd)
	fleetCmd.AddCommand(fleetPlantsCmd)
	fleetCmd.AddCommand(fleetNodesCmd)
	fleetCmd.AddCommand(fleetRegisterCmd)
	fleetCmd.AddCommand(fleetExerciseCmd)
}
