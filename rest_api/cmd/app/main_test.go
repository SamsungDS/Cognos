package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"flag"
	"fmt"
	"google.golang.org/grpc/grpclog"
	"io"
	"io/ioutil"
	"mime/multipart"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

var (
	logFile     string = "/var/log/svk/svk_mgmt_rest_api.log"
	errorString string = "Error in creating RestServer server interface"
	certsDir    string = "/etc/svk/certificates"
)

func setup(t *testing.T) {
	// Remove the certs directory and create a fresh directory
	// Otherwise, the certs file can cause the REST server to start in HTTPS mode
	err := os.RemoveAll(certsDir)
	if err != nil {
		t.Fatalf("Error removing certs directory: %v", err)
	}
	err = os.MkdirAll(certsDir, 0755)
	if err != nil {
		t.Fatalf("Error creating certs directory: %v", err)
	}
}

func stopServer(t *testing.T) {
	cmd := "kill -INT $(netstat -anp|grep 8001|awk '{print $NF}'|sed 's;/; ;g'|awk '{print $1}')"
	out, err := exec.Command("bash", "-c", cmd).Output()
	if err != nil {
		t.Fatalf("Error in sending the signal to the process %v", err)
	}
	if len(out) != 0 {
		t.Logf("Output %s", out)
	}
}

func TestConfigFile(t *testing.T) {
	setup(t)
	str := `{"svk_mgmt_rest_api":{"controller": {"id": "localhost","port": "9999"},"rest_server": {"id": "localhost","port": "8001"}}}`

	logFileHandle := InitLogger(logFile)
	defer logFileHandle.Close()
	err := os.WriteFile("conf.json", []byte(str), 0644)
	if err != nil {
		t.Fatalf("Error in creating conf.json file")
	}
	http_server_endpoint, https_server_endpoint, controller_endpoint := ReadConfigFileForServer("conf.json")
	if http_server_endpoint != "localhost:8001" {
		t.Fatalf("Result was incorrect, got: %s expected %s", http_server_endpoint, "localhost:8001")
	}
	if https_server_endpoint != "localhost:8443" {
		t.Fatalf("Result was incorrect, got: %s expected %s", https_server_endpoint, "localhost:8443")
	}
	if controller_endpoint != "localhost:9999" {
		t.Fatalf("Result was incorrect, got: %s expected %s", controller_endpoint, "localhost:9999")
	}
	os.Remove("conf.json")
}

func TestInitRestServer(t *testing.T) {
	setup(t)
	logFileHandle := InitLogger(logFile)

	svk_logger = grpclog.NewLoggerV2(logFileHandle, ioutil.Discard, ioutil.Discard)
	grpclog.SetLoggerV2(svk_logger)

	ctx := context.Background()
	certFile := ""
	keyFile := ""
	server, err := InitHTTPRestServer("localhost:8001", "localhost:9999", ctx, certFile, keyFile)
	if server == nil {
		t.Logf("Failed to start server: %v", err)
		t.Fatal(errorString)
	}
	CloseLogger(logFileHandle)
}

func IssueSignal(restServerChannel <-chan int) int {
	pid := <-restServerChannel

	time.Sleep(2 * time.Second)

	proc, err := os.FindProcess(pid)
	if err != nil {
		return -1
	}
	proc.Signal(syscall.SIGINT)
	return 0
}

func TestRunRestServer(t *testing.T) {
	setup(t)
	logFileHandle := InitLogger(logFile)

	svk_logger = grpclog.NewLoggerV2(logFileHandle, ioutil.Discard, ioutil.Discard)
	restServerChannel := make(chan int, 2)
	grpclog.SetLoggerV2(svk_logger)
	ctx := context.Background()
	certFile := ""
	keyFile := ""
	useTLS := false
	server, err := InitHTTPRestServer("localhost:8001", "localhost:9999", ctx, certFile, keyFile)
	if server == nil {
		t.Logf("Failed to start server: %v", err)
		t.Fatal(errorString)
	}
	InitSignalHandler(restServerChannel)
	go RunRestServer(server, useTLS)
	go IssueSignal(restServerChannel)
	StopRestServer(ctx)
	close(restServerChannel)
	CloseLogger(logFileHandle)
}

func TestRunRestServerWithCACertificates(t *testing.T) {
	setup(t)
	logFileHandle := InitLogger(logFile)

	log := grpclog.NewLoggerV2(logFileHandle, ioutil.Discard, ioutil.Discard)

	restServerChannel := make(chan int, 2)
	grpclog.SetLoggerV2(log)
	ctx := context.Background()
	dir, _ := os.Getwd()
	certFile := filepath.Join(dir, "../../ut_ca_certs/cert.pem.test")
	keyFile := filepath.Join(dir, "../../ut_ca_certs/key.pem.test")
	useTLS := true
	server, err := InitHTTPSRestServer("localhost:8443", "localhost:9999", ctx, certFile, keyFile)
	if server == nil {
		t.Logf("Failed to load TLS certificates: %v", err)
		t.Fatal(errorString)
	}
	InitSignalHandler(restServerChannel)
	go RunRestServer(server, useTLS)
	go IssueSignal(restServerChannel)
	StopRestServer(ctx)
	close(restServerChannel)
	CloseLogger(logFileHandle)
}

func TestRunRestServerWithInvalidCACertificates(t *testing.T) {
	setup(t)
	logFileHandle := InitLogger(logFile)
	svk_logger = grpclog.NewLoggerV2(logFileHandle, ioutil.Discard, ioutil.Discard)
	grpclog.SetLoggerV2(svk_logger)

	ctx := context.Background()
	dir, _ := os.Getwd()

	certFile := filepath.Join(dir, "../../ut_ca_certs/cert.pem.testx")
	keyFile := filepath.Join(dir, "../../ut_ca_certs/cert.pem.testx")
	server, err := InitHTTPSRestServer("localhost:8001", "localhost:9999", ctx, certFile, keyFile)
	if server != nil {
		t.Fatalf("Expected to fail in loading TLS certificates: %v", err)
	}
	CloseLogger(logFileHandle)
}

func createAndSendMultipartFormRequest(t *testing.T, url, certPath, keyPath string) (*http.Response, error) {
	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)

	// Create form file for certificate
	certPart, err := writer.CreateFormFile("certificate_pem_file", "cert.pem")
	if err != nil {
		return nil, err
	}

	certFile, err := os.Open(certPath)
	if err != nil {
		t.Fatalf("Error opening key file: %v", err)
	}
	defer certFile.Close()
	_, err = io.Copy(certPart, certFile)
	if err != nil {
		t.Fatalf("Error copying cert file: %v", err)
	}

	// Create form file for key
	keyPart, err := writer.CreateFormFile("key_pem_file", "key.pem")
	if err != nil {
		return nil, err
	}
	keyFile, err := os.Open(keyPath)
	if err != nil {
		t.Fatalf("Error opening key file: %v", err)
	}
	defer keyFile.Close()

	_, err = io.Copy(keyPart, keyFile)
	if err != nil {
		t.Fatalf("Error copying cert file: %v", err)
	}

	// Close the writer
	if err := writer.Close(); err != nil {
		return nil, err
	}

	// Create and send the request
	req, err := http.NewRequest("POST", url, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}

	return resp, nil
}

func createAndSendMultipartFormRequestForHTTPS(t *testing.T, url, certPath, keyPath string) (*http.Response, error) {
	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)

	oldCertPath := filepath.Join(certsDir, "cert.pem")
	oldKeyPath := filepath.Join(certsDir, "key.pem")

	// Load the certificate and key
	cert, load_err := tls.LoadX509KeyPair(oldCertPath, oldKeyPath)
	if load_err != nil {
		t.Fatalf("Error loading certificate: %v", load_err)
	}

	// Create a TLS configuration
	tlsConfig := &tls.Config{
		Certificates: []tls.Certificate{cert},
		// You might need to adjust this depending on your server's certificate
		InsecureSkipVerify: true, // For testing with self-signed certificates
	}

	// Create an HTTP client with the TLS configuration
	tr := &http.Transport{
		TLSClientConfig: tlsConfig,
	}
	client := &http.Client{Transport: tr}

	// Create form file for certificate
	certPart, err := writer.CreateFormFile("certificate_pem_file", "cert.pem")
	if err != nil {
		return nil, err
	}

	certFile, err := os.Open(certPath)
	if err != nil {
		t.Fatalf("Error opening key file: %v", err)
	}
	defer certFile.Close()
	_, err = io.Copy(certPart, certFile)
	if err != nil {
		t.Fatalf("Error copying cert file: %v", err)
	}

	// Create form file for key
	keyPart, err := writer.CreateFormFile("key_pem_file", "key.pem")
	if err != nil {
		return nil, err
	}
	keyFile, err := os.Open(keyPath)
	if err != nil {
		t.Fatalf("Error opening key file: %v", err)
	}
	defer keyFile.Close()

	_, err = io.Copy(keyPart, keyFile)
	if err != nil {
		t.Fatalf("Error copying cert file: %v", err)
	}

	// Close the writer
	if err := writer.Close(); err != nil {
		return nil, err
	}

	// Create and send the request
	req, err := http.NewRequest("POST", url, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}

	return resp, nil
}

var parseFlags = false

func TestMainFunction(t *testing.T) {
	setup(t)
	go func() {
		main()
	}()
	// svk_logger.Info("Testing main function")

	parseFlags = true
	time.Sleep(5 * time.Second)

	dir, _ := os.Getwd()

	// Prepare the request to upload the key/cert pem files to update the certificates
	url := "http://localhost:8001/UpdateCertificate"
	certPath := filepath.Join(dir, "../../ut_ca_certs/cert.pem.test")
	keyPath := filepath.Join(dir, "../../ut_ca_certs/key.pem.test")

	resp, err := createAndSendMultipartFormRequest(t, url, certPath, keyPath)
	if err != nil {
		t.Fatalf("Error sending request: %v", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("Error reading response body: %v", err)
	}

	// Check the response
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Expected status code %d, got %d", http.StatusOK, resp.StatusCode)
	}

	expectedStatusMessage := "Certificates created successfully. Requires a REST server restart to take effect"
	if !strings.Contains(string(body), expectedStatusMessage) {
		t.Fatalf("Expected status message to contain '%s', got '%s'", expectedStatusMessage, string(body))
	}

	defaultCertPath := certsDir + "/cert.pem"
	if !fileExists(defaultCertPath) {
		t.Fatalf("Didn't upload the certificates successfully")
	}

	stopServer(t)
}

func copyFile(src, dest string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dest, data, 0644)
}

// generateCerts generates cert.pem and key.pem files in the specified directory.
func generateCerts() error {
	// Create the certificates directory if it doesn't exist
	err := os.MkdirAll(certsDir, 0755)
	if err != nil {
		return err
	}

	// Generate private key
	keyPath := filepath.Join(certsDir, "new_key.pem")
	cmd := exec.Command("openssl", "genrsa", "-out", keyPath, "2048")
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("error generating private key: %v, output: %s", err, output)
	}

	// Generate certificate
	certPath := filepath.Join(certsDir, "new_cert.pem")
	cmd = exec.Command("openssl", "req", "-x509", "-new", "-nodes", "-key", keyPath, "-subj", "/C=US/ST=CA/L=SanJose/O=Samsung/CN=localhost", "-out", certPath)
	output, err = cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("error generating certificate: %v, output: %s", err, output)
	}

	return nil
}

// This function is to run the REST server in HTTPS mode by copying the certificates.
func TestHTTPSValidation(t *testing.T) {
	setup(t)

	if parseFlags == false {
		InitRestServerFlags()
		flag.Parse()
		parseFlags = true
		logFileHandle := InitLogger(logFile)
		defer logFileHandle.Close()
	}

	dir, _ := os.Getwd()
	certPath := filepath.Join(dir, "../../ut_ca_certs/cert.pem.test")
	keyPath := filepath.Join(dir, "../../ut_ca_certs/key.pem.test")

	// Copy certificate and key files
	err := copyFile(certPath, filepath.Join(certsDir, "cert.pem"))
	if err != nil {
		t.Fatalf("Failed to copy cert file: %v", err)
		os.Exit(1)
	}

	err = copyFile(keyPath, filepath.Join(certsDir, "key.pem"))
	if err != nil {
		t.Fatalf("Failed to copy key file: %v", err)
		os.Exit(1)
	}

	ctx, cancel := context.WithCancel(context.Background())

	go func() {
		MainWithContext(ctx)
	}()
	time.Sleep(2 * time.Second)

	// Check for the string  "TLS key and cert files exist. Running the HTTPS mode" in the log file
	logContent, err := ioutil.ReadFile(logFile)
	if err != nil {
		t.Fatalf("Error reading log file: %v", err)
	}

	expectedString := "TLS key and cert files exist. Running the HTTPS mode as well"
	if !bytes.Contains(logContent, []byte(expectedString)) {
		t.Errorf("Expected log to contain '%s', but it did not", expectedString)
	}

	// Upload the new certificate and check whether the command succeeds or not
	err = generateCerts()
	if err != nil {
		t.Fatalf("Error generating certs: %v", err)
	}

	url := "https://localhost:8443/UpdateCertificate"
	certPath = filepath.Join(certsDir, "new_cert.pem")
	keyPath = filepath.Join(certsDir, "new_key.pem")

	resp, err := createAndSendMultipartFormRequestForHTTPS(t, url, certPath, keyPath)
	if err != nil {
		t.Fatalf("Error sending request: %v", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("Error reading response body: %v", err)
	}

	// Check the response
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Expected status code %d, got %d", http.StatusOK, resp.StatusCode)
	}

	expectedStatusMessage := "Certificates updated successfully. Use the new certificate to access the HTTPS server"
	if !strings.Contains(string(body), expectedStatusMessage) {
		t.Errorf("Expected status message to contain '%s', got '%s'", expectedStatusMessage, string(body))
	}

	stopServer(t)

	cancel()
}

func TestMainWithInvalidURL(t *testing.T) {
	setup(t)

	if parseFlags == false {
		InitRestServerFlags()
		flag.Parse()
		parseFlags = true
		logFileHandle := InitLogger(logFile)
		defer logFileHandle.Close()
	}

	ctx, cancel := context.WithCancel(context.Background())

	go func() {
		MainWithContext(ctx)
	}()
	time.Sleep(5 * time.Second)

	dir, _ := os.Getwd()

	// Prepare the request to upload the key/cert pem files to update the certificates
	certPath := filepath.Join(dir, "../../ut_ca_certs/cert.pem.test")
	keyPath := filepath.Join(dir, "../../ut_ca_certs/key.pem.test")
	invalidUrl := "http://localhost:8001/DummyUpdateCertificate"

	resp, err := createAndSendMultipartFormRequest(t, invalidUrl, certPath, keyPath)
	if err != nil {
		t.Fatalf("Error sending request: %v", err)
	}
	defer resp.Body.Close()

	// Check the response
	if resp.StatusCode == http.StatusOK {
		t.Fatalf("Expected status code %d, got %d", http.StatusOK, resp.StatusCode)
	}
	stopServer(t)
	cancel()
}
