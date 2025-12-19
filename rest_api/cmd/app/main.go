package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"flag"
	"io"
	"io/fs"
	"io/ioutil"
	"log"
	"mime"
	"mime/multipart"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/grpc-ecosystem/grpc-gateway/v2/runtime"
	"google.golang.org/grpc"
	"google.golang.org/grpc/grpclog"
	svkfwprotobuf "rest_api/api/framework"
	"rest_api/third_party"
)

var svk_logger grpclog.LoggerV2

// getOpenAPIHandler serves an OpenAPI UI.
func getOpenAPIHandler() http.Handler {
	mime.AddExtensionType(".svg", "image/svg+xml")
	subFS, err := fs.Sub(third_party.OpenAPI, "OpenAPI")
	if err != nil {
		panic("couldn't create sub filesystem: " + err.Error())
	}
	return http.FileServer(http.FS(subFS))
}

func readConfigFileForServer(configFile string) (string, string) {
	var controllerId string
	var restServerId string

	type Controller struct {
		Id   string `json:"id"`
		Port string `json:"port"`
	}
	type RestServer struct {
		Id   string `json:"id"`
		Port string `json:"port"`
	}

	fileContent, err := os.Open(configFile)
	if err != nil {
		log.Fatal(err)
		return "", ""
	}

	byteResult, _ := ioutil.ReadAll(fileContent)
	fileContent.Close()

	// Read the json file
	var sections map[string]json.RawMessage
	json.Unmarshal([]byte(byteResult), &sections)

	// Read the svk_mgmt_rest_api section
	var restapi map[string]json.RawMessage
	json.Unmarshal(sections["svk_mgmt_rest_api"], &restapi)

	// Read the controller section from svk_mgmt_rest_api section
	var controller Controller
	json.Unmarshal(restapi["controller"], &controller)

	// Read the rest_server section from svk_mgmt_rest_api section
	var restserver RestServer
	json.Unmarshal(restapi["rest_server"], &restserver)

	// If the entries are not present in controller section, override
	// with the default values or the command line value
	if len(controller.Id) != 0 {
		controllerId = controller.Id + ":" + controller.Port
	} else {
		controllerId = ""
	}

	if len(restserver.Id) != 0 {
		restServerId = restserver.Id + ":" + restserver.Port
	} else {
		restServerId = ""
	}

	return restServerId, controllerId
}

func readConfigFileForLogger(configFile string) string {
	type Logger struct {
		FileName string `json:"log_file_name"`
	}

	fileContent, err := os.Open(configFile)
	if err != nil {
		log.Fatal(err)
		return ""
	}

	byteResult, _ := ioutil.ReadAll(fileContent)
	fileContent.Close()

	// Read the json file
	var sections map[string]json.RawMessage
	json.Unmarshal([]byte(byteResult), &sections)

	// Read the svk_mgmt_rest_api section
	var restapi map[string]json.RawMessage
	json.Unmarshal(sections["svk_mgmt_rest_api"], &restapi)

	// Read the logger section from svk_mgmt_rest_api section
	var logger Logger
	json.Unmarshal(restapi["logger"], &logger)

	return logger.FileName
}

/**
	This function parses the HTTP request for multipart form format.
	Reads the data of the entries "certificate_pem_file" and "key_pem_file" and
	saves the data into the /etc/svk/certificates folder as cert.pem and key.pem respectively.
	Return either error or success by HTTP status code.
*/

func updateCertificatesHandler(server *http.Server, certFile *string, keyFile *string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Invalid request method", http.StatusBadRequest)
			return
		}

		err := r.ParseMultipartForm(10 << 20) // 10 MB
		if err != nil {
			http.Error(w, "Failed to parse form", http.StatusBadRequest)
			return
		}

		svk_logger.Info("Retrieving certificate and key PEM files")
		cert, _, err := r.FormFile("certificate_pem_file")
		if err != nil {
			http.Error(w, "Failed to retrieve certificate file", http.StatusBadRequest)
			return
		}
		defer cert.Close()

		key, _, err := r.FormFile("key_pem_file")
		if err != nil {
			http.Error(w, "Failed to retrieve key file", http.StatusBadRequest)
			return
		}
		defer key.Close()
		svk_logger.Info("Retrieved certificate and key PEM files")

		// Save the uploaded files
		svk_logger.Info("Saving certificate and key files to local system")
		svk_logger.Infof("Saving certificate file to %s", *certFile)
		err = saveFile(cert, *certFile)
		if err != nil {
			http.Error(w, "Failed to save certificate file", http.StatusInternalServerError)
			return
		}

		svk_logger.Infof("Saving key file to %s", *keyFile)
		err = saveFile(key, *keyFile)
		if err != nil {
			http.Error(w, "Failed to save key file", http.StatusInternalServerError)
			os.Remove(*certFile)
			return
		}
		svk_logger.Info("Saved certificate and key files to local system")

		err = createTLSServer(server, *certFile, *keyFile)
		if err != nil {
			svk_logger.Error("Failed in creating HTTPS server configuration")
			http.Error(w, "Failed to load TLS configuration. Check the key and the certificate files", http.StatusInternalServerError)
			os.Remove(*certFile)
			os.Remove(*keyFile)
			return
		}

		svk_logger.Info("Certificates updated successfully")

		w.WriteHeader(http.StatusOK)
		w.Write([]byte("Certificates updated successfully. Requires a REST server restart to take effect"))
	}
}

func saveFile(file multipart.File, filename string) error {
	dir := filepath.Dir(filename)
	err := os.MkdirAll(dir, os.ModePerm)
	if err != nil {
		svk_logger.Errorf("Failed to create directory %s: %v", dir, err)
		return err
	}

	out, err := os.Create(filename)
	if err != nil {
		svk_logger.Errorf("Failed to create filename %s: %v", filename, err)
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, file)
	svk_logger.Info("Copying to filename %s: %v", filename, err)

	return err
}

func debugFnHandler(w http.ResponseWriter, r *http.Request) {

	svk_logger.Infof("Received request: URL Path = %s, URL RawQuery = %s", r.URL.Path, r.URL.RawQuery)
	queryArgs := r.URL.Query()
	svk_logger.Infof("Query Args: %+v ", queryArgs)

	// Log the request body
	if r.Method == http.MethodPost || r.Method == http.MethodPut {
		var buf bytes.Buffer
		_, err := buf.ReadFrom(r.Body)
		if err != nil {
			svk_logger.Error("Error reading request body: %v", err)
		} else {
			svk_logger.Infof("Request Body: %s ", buf.String())
			// Reset the request body so it can be read again
			r.Body = io.NopCloser(bytes.NewBuffer(buf.Bytes()))
		}
	}
}

func createTLSServer(server *http.Server, certFile string, keyFile string) error {
	svk_logger.Info("Creating/Reloading HTTPS server")
	// Load TLS certificates
	cert, err := tls.LoadX509KeyPair(certFile, keyFile)
	if err != nil {
		svk_logger.Error("Failed to load TLS certificates: %v", err)
		return err
	}

	// Create a TLS configuration
	tlsConfig := &tls.Config{
		Certificates: []tls.Certificate{cert},
		MinVersion:   tls.VersionTLS12, // Minimum TLS version
	}

	// Create an HTTPS server
	server.TLSConfig = tlsConfig
	svk_logger.Info("Created/Reloaded HTTPS server")
	return nil
}

func InitRestServer(restServerId string, controllerId string, ctx context.Context, certFile string, keyFile string) (*http.Server, error) {
	var server *http.Server

	// creating mux for gRPC gateway. This will multiplex or route request different gRPC service
	mux := runtime.NewServeMux()

	// setting up a dial up for gRPC service by specifying endpoint/target url
	err := svkfwprotobuf.RegisterControllerHandlerFromEndpoint(ctx, mux, controllerId, []grpc.DialOption{grpc.WithInsecure()})
	if err != nil {
		svk_logger.Fatal(err)
	}

	oa := getOpenAPIHandler()
	server = &http.Server{
		Addr: restServerId,
		Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// TODO: Fix after adding additional debug levels
			// debugFnHandler(w, r)
			if strings.HasPrefix(r.URL.Path, "/api") {
				// Landing function going to the controller API
				mux.ServeHTTP(w, r)
				return
			} else if strings.ToLower(r.URL.Path) == "/updatecertificate" {
				// Function to update the certificates in multipart upload
				// User/Admin uploads the files using multipart option.
				svk_logger.Info("Update certificates call received")
				updateCertificatesHandler(server, &certFile, &keyFile)(w, r)
				return
			}
			oa.ServeHTTP(w, r)

		}),
	}

	if fileExists(certFile) && fileExists(keyFile) {
		svk_logger.Info("Creating HTTPS server configuration")
		err = createTLSServer(server, certFile, keyFile)
		if err != nil {
			svk_logger.Error("Failed in creating HTTPS server configuration")
			return nil, err
		}
		svk_logger.Info("Creating HTTPS server configuration succeeded")
	}

	svk_logger.Info("Serving gRPC-Gateway and OpenAPI Documentation on https://", restServerId)
	return server, nil
}

func RunRestServer(server *http.Server, restServerChannel chan<- int, useTLS bool) int {

	pid := os.Getpid()
	select {
	case restServerChannel <- pid:
		// message sent
		svk_logger.Info("Sent the PID to the server channel ", pid)
	default:
		// message dropped
		svk_logger.Error("Couldn't send the PID to the server channel")
	}
	svk_logger.Info("Started serving new connections on gRPC-Gateway.")
	var err error
	if useTLS {
		err = server.ListenAndServeTLS("", "")
	} else {
		err = server.ListenAndServe()
	}
	if !errors.Is(err, http.ErrServerClosed) {
		svk_logger.Fatalf("gRPC-Gateway server error: %v", err)
	}
	svk_logger.Info("Stopped serving new connections on gRPC-Gateway.")

	return pid
}

func StopRestServer(server *http.Server, ctx context.Context) int {
	ret := -1

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	s := <-sigChan

	svk_logger.Info("Received signal to the server -> ", s)

	shutdownCtx, shutdownRelease := context.WithTimeout(ctx, 10*time.Second)
	defer shutdownRelease()

	if err := server.Shutdown(shutdownCtx); err != nil {
		svk_logger.Fatalf("gRPC-Gateway server shutdown error: %v", err)
	} else {
		svk_logger.Info("Graceful gRPC-Gateway server shutdown complete.")
		ret = 0
	}

	return ret
}

func fileExists(filename string) bool {
	_, err := os.Stat(filename)
	return err == nil
}

func initRestServerFlags() {
	flag.String("grpc_server_endpoint", "localhost:8001", "gRPC server endpoint")
	flag.String("grpc_controller_server", "localhost:9999", "gRPC Controller server endpoint")
	flag.String("config_file", "/usr/local/svk/conf.json", "Configuration file to read controller and server details")
	flag.String("cert_file", "/etc/svk/certificates/cert.pem", "TLS certificate file")
	flag.String("key_file", "/etc/svk/certificates/key.pem", "TLS key file")
}

func mainWithContext(ctx context.Context) {
	grpcServerEndpoint := flag.Lookup("grpc_server_endpoint").Value.String()
	grpcControllerServer := flag.Lookup("grpc_controller_server").Value.String()
	configFile := flag.Lookup("config_file").Value.String()
	certFile := flag.Lookup("cert_file").Value.String()
	keyFile := flag.Lookup("key_file").Value.String()

	useTLS := false

	restServerId, controllerId := readConfigFileForServer(configFile)
	logFileName := readConfigFileForLogger(configFile)
	restServerChannel := make(chan int, 2)

	if len(logFileName) == 0 {
		logFileName = "/var/log/svk/svk_mgmt_rest_api.log"
	}

	logFileHandle, err := os.OpenFile(logFileName, os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		if os.IsNotExist(err) {
			logFileHandle, err = os.OpenFile(logFileName, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
			if err != nil {
				log.Fatalf("Failed to create logger file: %v", logFileName)
			}
		} else {
			log.Fatalf("Failed to open logger file: %v", logFileName)
		}
	}
	defer logFileHandle.Close()

	svk_logger = grpclog.NewLoggerV2(logFileHandle, logFileHandle, logFileHandle)
	grpclog.SetLoggerV2(svk_logger)
	svk_logger.Infof("Initialized the logger to the file %s", logFileName)

	// Check the certificate files and run in HTTP/HTTPS mode
	if fileExists(certFile) && fileExists(keyFile) {
		svk_logger.Info("TLS key and cert files exist. Running in HTTPS mode")
		useTLS = true
	} else {
		svk_logger.Info("TLS key and cert files do not exist. Running in HTTP mode")
	}

	// If the entries are not present in controller section, override
	// with the default values or the command line value
	if len(controllerId) == 0 {
		controllerId = grpcControllerServer
	}

	if len(restServerId) == 0 {
		restServerId = grpcServerEndpoint
	}

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	server, err := InitRestServer(restServerId, controllerId, ctx, certFile, keyFile)
	if err != nil {
		svk_logger.Fatal(err)
	}
	go RunRestServer(server, restServerChannel, useTLS)

	StopRestServer(server, ctx)
	close(restServerChannel)
}

func main() {
	// Separate the flag parsing outside the main function so that the UTs when called multiple times
	// under the same context will throw error "flag redefined"
	initRestServerFlags()
	flag.Parse()

	mainWithContext(context.Background())
}
