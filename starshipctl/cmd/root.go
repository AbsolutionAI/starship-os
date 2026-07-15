package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

var rootCmd = &cobra.Command{
	Use:   "starshipctl",
	Short: "Starship OS CLI",
	Long:  "Starship OS - a native AI operating system for complex system control",
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Println("Starship OS CLI")
	},
}

func Execute() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
}

func init() {
	rootCmd.AddCommand(versionCmd)
}
