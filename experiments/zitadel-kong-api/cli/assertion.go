package main

import (
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"os"
	"time"
)

// keyFile mirrors the JSON Zitadel emits for a Private Key JWT credential.
// Service-user keys carry "userId"; application keys carry "appId"/"clientId".
type keyFile struct {
	Type     string `json:"type"`
	KeyID    string `json:"keyId"`
	Key      string `json:"key"`
	AppID    string `json:"appId"`
	ClientID string `json:"clientId"`
	UserID   string `json:"userId"`
}

func loadKeyFile(path string) (*keyFile, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var kf keyFile
	if err := json.Unmarshal(b, &kf); err != nil {
		return nil, fmt.Errorf("parsing key file: %w", err)
	}
	if kf.Key == "" || kf.KeyID == "" {
		return nil, fmt.Errorf("key file missing \"key\" or \"keyId\"")
	}
	return &kf, nil
}

// subject is the JWT iss/sub: the userId for service-user keys, else the clientId.
func (kf *keyFile) subject() string {
	if kf.UserID != "" {
		return kf.UserID
	}
	return kf.ClientID
}

func b64url(b []byte) string { return base64.RawURLEncoding.EncodeToString(b) }

func parseRSAPrivateKey(pemStr string) (*rsa.PrivateKey, error) {
	block, _ := pem.Decode([]byte(pemStr))
	if block == nil {
		return nil, fmt.Errorf("could not decode PEM private key")
	}
	if k, err := x509.ParsePKCS1PrivateKey(block.Bytes); err == nil {
		return k, nil
	}
	k, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("parsing private key: %w", err)
	}
	rk, ok := k.(*rsa.PrivateKey)
	if !ok {
		return nil, fmt.Errorf("key is not RSA (%T)", k)
	}
	return rk, nil
}

// buildAssertion creates a signed RS256 JWT bearer assertion for `audience`
// (Zitadel's issuer), valid for one hour.
func buildAssertion(kf *keyFile, audience string, now time.Time) (string, error) {
	priv, err := parseRSAPrivateKey(kf.Key)
	if err != nil {
		return "", err
	}
	sub := kf.subject()
	header, _ := json.Marshal(map[string]string{"alg": "RS256", "typ": "JWT", "kid": kf.KeyID})
	claims, _ := json.Marshal(map[string]any{
		"iss": sub,
		"sub": sub,
		"aud": audience,
		"iat": now.Unix(),
		"exp": now.Add(time.Hour).Unix(),
	})

	signingInput := b64url(header) + "." + b64url(claims)
	digest := sha256.Sum256([]byte(signingInput))
	sig, err := rsa.SignPKCS1v15(rand.Reader, priv, crypto.SHA256, digest[:])
	if err != nil {
		return "", err
	}
	return signingInput + "." + b64url(sig), nil
}
