package main

import (
	"bytes"
	"context"
	"google.golang.org/grpc/grpclog"
	"io"
	"io/ioutil"
	"mime/multipart"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
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

	err := os.WriteFile("conf.json", []byte(str), 0644)
	if err != nil {
		t.Fatalf("Error in creating conf.json file")
	}
	restServerId, controllerId := readConfigFileForServer("conf.json")
	if restServerId != "localhost:8001" {
		t.Fatalf("Result was incorrect, got: %s expected %s", restServerId, "localhost:8001")
	}
	if controllerId != "localhost:9999" {
		t.Fatalf("Result was incorrect, got: %s expected %s", controllerId, "localhost:9999")
	}
	os.Remove("conf.json")
}

func TestInitRestServer(t *testing.T) {
	setup(t)
	logFileHandle, _ := os.OpenFile(logFile, os.O_WRONLY|os.O_APPEND, 0644)

	svk_logger = grpclog.NewLoggerV2(logFileHandle, ioutil.Discard, ioutil.Discard)
	grpclog.SetLoggerV2(svk_logger)

	ctx := context.Background()
	certFile := ""
	keyFile := ""
	server, err := InitRestServer("localhost:8001", "localhost:9999", ctx, certFile, keyFile)
	if server == nil {
		t.Logf("Failed to start server: %v", err)
		t.Fatalf(errorString)
	}
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
	logFileHandle, _ := os.OpenFile(logFile, os.O_WRONLY|os.O_APPEND, 0644)

	svk_logger = grpclog.NewLoggerV2(logFileHandle, ioutil.Discard, ioutil.Discard)
	restServerChannel := make(chan int, 2)
	grpclog.SetLoggerV2(svk_logger)
	ctx := context.Background()
	certFile := ""
	keyFile := ""
	useTLS := false
	server, err := InitRestServer("localhost:8001", "localhost:9999", ctx, certFile, keyFile)
	if server == nil {
		t.Logf("Failed to start server: %v", err)
		t.Fatalf(errorString)
	}
	go RunRestServer(server, restServerChannel, useTLS)
	go IssueSignal(restServerChannel)
	StopRestServer(server, ctx)
	close(restServerChannel)
}

func TestRunRestServerWithCACertificates(t *testing.T) {
	setup(t)
	logFileHandle, _ := os.OpenFile(logFile, os.O_WRONLY|os.O_APPEND, 0644)

	log := grpclog.NewLoggerV2(logFileHandle, ioutil.Discard, ioutil.Discard)

	restServerChannel := make(chan int, 2)
	grpclog.SetLoggerV2(log)
	ctx := context.Background()
	dir, _ := os.Getwd()
	certFile := filepath.Join(dir, "../../ut_ca_certs/cert.pem.test")
	keyFile := filepath.Join(dir, "../../ut_ca_certs/key.pem.test")
	useTLS := true
	server, err := InitRestServer("localhost:8001", "localhost:9999", ctx, certFile, keyFile)
	if server == nil {
		t.Logf("Failed to load TLS certificates: %v", err)
		t.Fatalf(errorString)
	}
	go RunRestServer(server, restServerChannel, useTLS)
	go IssueSignal(restServerChannel)
	StopRestServer(server, ctx)
	close(restServerChannel)
}

func TestRunRestServerWithInvalidCACertificates(t *testing.T) {
	setup(t)
	logFileHandle, _ := os.OpenFile(logFile, os.O_WRONLY|os.O_APPEND, 0644)
	svk_logger = grpclog.NewLoggerV2(logFileHandle, ioutil.Discard, ioutil.Discard)
	grpclog.SetLoggerV2(svk_logger)

	ctx := context.Background()
	dir, _ := os.Getwd()

	certFile := filepath.Join(dir, "../../ut_ca_certs/cert.pem.test")
	keyFile := filepath.Join(dir, "../../ut_ca_certs/cert.pem.test")
	server, err := InitRestServer("localhost:8001", "localhost:9999", ctx, certFile, keyFile)
	if server != nil {
		t.Fatalf("Expected to fail in loading TLS certificates: %v", err)
	}
}

func TestMainFunction(t *testing.T) {
	setup(t)

	go func() {
		main()
	}()
	time.Sleep(5 * time.Second)

	dir, _ := os.Getwd()

	// Prepare the request to upload the key/cert pem files to update the certificates
	url := "http://localhost:8001/UpdateCertificate"
	certPath := filepath.Join(dir, "../../ut_ca_certs/cert.pem.test")
	keyPath := filepath.Join(dir, "../../ut_ca_certs/key.pem.test")

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	certPart, err := writer.CreateFormFile("certificate_pem_file", "cert.pem")
	if err != nil {
		t.Fatalf("Error creating form file for cert: %v", err)
	}
	certFile, err := os.Open(certPath)
	if err != nil {
		t.Fatalf("Error opening cert file: %v", err)
	}
	defer certFile.Close()
	_, err = io.Copy(certPart, certFile)
	if err != nil {
		t.Fatalf("Error copying cert file: %v", err)
	}

	keyPart, err := writer.CreateFormFile("key_pem_file", "key.pem")
	if err != nil {
		t.Fatalf("Error creating form file for key: %v", err)
	}

	keyFile, err := os.Open(keyPath)
	if err != nil {
		t.Fatalf("Error opening key file: %v", err)
	}
	defer keyFile.Close()
	_, err = io.Copy(keyPart, keyFile)
	if err != nil {
		t.Fatalf("Error copying key file: %v", err)
	}

	err = writer.Close()
	if err != nil {
		t.Fatalf("Error closing writer: %v", err)
	}

	req, err := http.NewRequest("POST", url, body)
	if err != nil {
		t.Fatalf("Error creating request: %v", err)
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())

	// Send the request
	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("Error sending request: %v", err)
	}
	defer resp.Body.Close()

	// Check the response
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Expected status code %d, got %d", http.StatusOK, resp.StatusCode)
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

// This function is to run the REST server in HTTPS mode by copying the certificates.
func TestHTTPSValidation(t *testing.T) {
	setup(t)

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
		mainWithContext(ctx)
	}()
	time.Sleep(2 * time.Second)

	cancel()
	time.Sleep(2 * time.Second)

	// Check for the string  "TLS key and cert files exist. Running in HTTPS mode" in the log file
	logContent, err := ioutil.ReadFile(logFile)
	if err != nil {
		t.Fatalf("Error reading log file: %v", err)
	}

	expectedString := "TLS key and cert files exist. Running in HTTPS mode"
	if !bytes.Contains(logContent, []byte(expectedString)) {
		t.Errorf("Expected log to contain '%s', but it did not", expectedString)
	}
	stopServer(t)
}

func TestMainWithInvalidURL(t *testing.T) {
	setup(t)

	ctx, cancel := context.WithCancel(context.Background())

	go func() {
		mainWithContext(ctx)
	}()
	time.Sleep(5 * time.Second)

	dir, _ := os.Getwd()

	// Prepare the request to upload the key/cert pem files to update the certificates
	certPath := filepath.Join(dir, "../../ut_ca_certs/cert.pem.test")
	keyPath := filepath.Join(dir, "../../ut_ca_certs/key.pem.test")
	invalidUrl := "http://localhost:8001/DummyUpdateCertificate"

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	certPart, err := writer.CreateFormFile("certificate_pem_file", "cert.pem")
	if err != nil {
		t.Fatalf("Error creating form file for cert: %v", err)
	}
	certFile, err := os.Open(certPath)
	if err != nil {
		t.Fatalf("Error opening cert file: %v", err)
	}
	defer certFile.Close()
	_, err = io.Copy(certPart, certFile)
	if err != nil {
		t.Fatalf("Error copying cert file: %v", err)
	}

	keyPart, err := writer.CreateFormFile("key_pem_file", "key.pem")
	if err != nil {
		t.Fatalf("Error creating form file for key: %v", err)
	}

	keyFile, err := os.Open(keyPath)
	if err != nil {
		t.Fatalf("Error opening key file: %v", err)
	}
	defer keyFile.Close()
	_, err = io.Copy(keyPart, keyFile)
	if err != nil {
		t.Fatalf("Error copying key file: %v", err)
	}

	err = writer.Close()
	if err != nil {
		t.Fatalf("Error closing writer: %v", err)
	}

	req, err := http.NewRequest("POST", invalidUrl, body)
	if err != nil {
		t.Fatalf("Error creating request: %v", err)
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())

	// Send the request
	client := &http.Client{}
	resp, err := client.Do(req)
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
