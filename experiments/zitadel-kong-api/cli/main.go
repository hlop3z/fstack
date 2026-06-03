// Command zk is a tiny, dependency-free helper for the Zitadel + Kong + API
// stack. It replaces the old Python config generator and the shell token
// scripts with a single static binary.
//
//	zk gen-config   render Kong's declarative config from Zitadel's JWKS
//	zk token        fetch a JWT access token via the client_credentials grant
package main

import (
	"fmt"
	"os"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}

	var err error
	switch os.Args[1] {
	case "gen-config":
		err = runGenConfig(os.Args[2:])
	case "token":
		err = runToken(os.Args[2:])
	case "-h", "--help", "help":
		usage()
		return
	default:
		fmt.Fprintf(os.Stderr, "zk: unknown command %q\n\n", os.Args[1])
		usage()
		os.Exit(2)
	}

	if err != nil {
		fmt.Fprintf(os.Stderr, "zk %s: %v\n", os.Args[1], err)
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprint(os.Stderr, `zk — Zitadel + Kong helper

Usage:
  zk gen-config [flags]   Fetch Zitadel's signing key and write kong.yml
  zk token      [flags]   Print a JWT access token (client_credentials grant)

Run "zk <command> -h" for command-specific flags.
All flags fall back to the matching environment variable.
`)
}

// env returns the value of key, or def when unset/empty.
func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
