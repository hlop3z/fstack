package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

// runToken fetches a JWT access token from Zitadel and prints ONLY the token to
// stdout, so it can be captured:
//
//	TOKEN=$(zk token --key-file key.json)
//	curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/hello
//
// Two credential types are supported:
//   - --key-file : a Zitadel Private Key JWT credential (RSA key JSON)
//   - --client-secret : a client_credentials secret (Basic auth)
func runToken(args []string) error {
	fs := flag.NewFlagSet("token", flag.ExitOnError)
	issuer := fs.String("issuer", env("ZITADEL_ISSUER", "http://localhost:8080"), "Zitadel issuer / token endpoint base")
	keyFilePath := fs.String("key-file", env("ZITADEL_KEY_FILE", ""), "path to a Zitadel Private Key JWT credential (JSON)")
	clientID := fs.String("client-id", env("ZITADEL_CLIENT_ID", ""), "OAuth client id (client_secret mode)")
	clientSecret := fs.String("client-secret", env("ZITADEL_CLIENT_SECRET", ""), "OAuth client secret (client_secret mode)")
	scope := fs.String("scope", env("ZITADEL_SCOPE", "openid profile"), "space-separated scopes")
	fs.Parse(args)

	issuerClean := strings.TrimRight(*issuer, "/")
	endpoint := issuerClean + "/oauth/v2/token"

	if *keyFilePath != "" {
		return tokenFromKey(endpoint, issuerClean, *keyFilePath, *scope)
	}

	if *clientID == "" || *clientSecret == "" {
		return fmt.Errorf("provide --key-file, or both --client-id and --client-secret " +
			"(env ZITADEL_KEY_FILE, or ZITADEL_CLIENT_ID/ZITADEL_CLIENT_SECRET)")
	}
	tok, status, body := postToken(endpoint, url.Values{
		"grant_type": {"client_credentials"},
		"scope":      {*scope},
	}, *clientID, *clientSecret)
	if tok == "" {
		return fmt.Errorf("client_credentials grant failed (%s): %s", status, body)
	}
	fmt.Println(tok)
	return nil
}

// tokenFromKey signs a JWT assertion with the private key and exchanges it.
// It first tries the JWT-bearer profile grant (service-user keys), then falls
// back to client_credentials with a private_key_jwt client assertion (app keys).
func tokenFromKey(endpoint, audience, keyPath, scope string) error {
	kf, err := loadKeyFile(keyPath)
	if err != nil {
		return err
	}
	assertion, err := buildAssertion(kf, audience, time.Now())
	if err != nil {
		return err
	}

	// Attempt 1: JWT profile (urn:...:jwt-bearer) — the assertion is the auth.
	tok, status, body := postToken(endpoint, url.Values{
		"grant_type": {"urn:ietf:params:oauth:grant-type:jwt-bearer"},
		"scope":      {scope},
		"assertion":  {assertion},
	}, "", "")
	if tok != "" {
		tokenLogf("authenticated via jwt-bearer profile (sub=%s)", kf.subject())
		fmt.Println(tok)
		return nil
	}
	tokenLogf("jwt-bearer profile grant failed (%s): %s", status, body)

	// Attempt 2: client_credentials with private_key_jwt client authentication.
	tok2, status2, body2 := postToken(endpoint, url.Values{
		"grant_type":            {"client_credentials"},
		"scope":                 {scope},
		"client_assertion_type": {"urn:ietf:params:oauth:client-assertion-type:jwt-bearer"},
		"client_assertion":      {assertion},
	}, "", "")
	if tok2 != "" {
		tokenLogf("authenticated via client_credentials + private_key_jwt (client=%s)", kf.ClientID)
		fmt.Println(tok2)
		return nil
	}

	return fmt.Errorf("both grants failed:\n  jwt-bearer profile:        %s: %s\n  client_credentials assert: %s: %s",
		status, body, status2, body2)
}

// postToken performs the form POST and returns (access_token, status, raw body).
// access_token is "" on any non-200 or missing-token response.
func postToken(endpoint string, form url.Values, basicUser, basicPass string) (token, status, body string) {
	req, err := http.NewRequest(http.MethodPost, endpoint, strings.NewReader(form.Encode()))
	if err != nil {
		return "", "request error", err.Error()
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	if basicUser != "" {
		req.SetBasicAuth(basicUser, basicPass)
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return "", "connection error", err.Error()
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	trimmed := strings.TrimSpace(string(raw))
	if resp.StatusCode != http.StatusOK {
		return "", resp.Status, trimmed
	}
	var out struct {
		AccessToken string `json:"access_token"`
	}
	_ = json.Unmarshal(raw, &out)
	return out.AccessToken, resp.Status, trimmed
}

func tokenLogf(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "[zk token] "+format+"\n", a...)
}
