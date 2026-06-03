package main

import (
	"crypto/rsa"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"strings"
	"time"
)

var httpClient = &http.Client{Timeout: 10 * time.Second}

// newRequest builds a request, overriding the Host header when host != "".
// Zitadel sits behind Traefik (routes on Host(`localhost`)), so we must send
// that header even when dialing host.docker.internal.
func newRequest(method, url, host string, body io.Reader) (*http.Request, error) {
	req, err := http.NewRequest(method, url, body)
	if err != nil {
		return nil, err
	}
	if host != "" {
		req.Host = host
	}
	return req, nil
}

type jwk struct {
	Kty string `json:"kty"`
	Use string `json:"use"`
	Kid string `json:"kid"`
	N   string `json:"n"`
	E   string `json:"e"`
}

type jwksDoc struct {
	Keys []jwk `json:"keys"`
}

// fetchSigningPEM downloads Zitadel's JWKS and returns the active RSA signing
// key as a PEM-encoded SubjectPublicKeyInfo, along with its kid.
func fetchSigningPEM(internalURL, host string) (pemStr, kid string, err error) {
	url := internalURL + "/oauth/v2/keys"
	req, err := newRequest(http.MethodGet, url, host, nil)
	if err != nil {
		return "", "", err
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return "", "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 200))
		return "", "", fmt.Errorf("GET %s: %s: %s", url, resp.Status, strings.TrimSpace(string(b)))
	}

	var doc jwksDoc
	if err := json.NewDecoder(resp.Body).Decode(&doc); err != nil {
		return "", "", fmt.Errorf("decoding JWKS: %w", err)
	}
	for _, k := range doc.Keys {
		if k.Kty != "RSA" || (k.Use != "" && k.Use != "sig") {
			continue
		}
		p, err := jwkToPEM(k)
		if err != nil {
			return "", "", err
		}
		return p, k.Kid, nil
	}
	return "", "", fmt.Errorf("no RSA signing key found in JWKS at %s", url)
}

func jwkToPEM(k jwk) (string, error) {
	nb, err := base64.RawURLEncoding.DecodeString(k.N)
	if err != nil {
		return "", fmt.Errorf("decoding modulus: %w", err)
	}
	eb, err := base64.RawURLEncoding.DecodeString(k.E)
	if err != nil {
		return "", fmt.Errorf("decoding exponent: %w", err)
	}
	pub := &rsa.PublicKey{
		N: new(big.Int).SetBytes(nb),
		E: int(new(big.Int).SetBytes(eb).Int64()),
	}
	der, err := x509.MarshalPKIXPublicKey(pub)
	if err != nil {
		return "", err
	}
	block := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der})
	return strings.TrimSpace(string(block)), nil
}
