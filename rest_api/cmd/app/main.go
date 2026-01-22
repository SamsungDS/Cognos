/**
 * @file main.go
 * @brief Main entry point for the REST API server.
 */
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
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/grpc-ecosystem/grpc-gateway/v2/runtime"
	"google.golang.org/grpc"
	"google.golang.org/grpc/grpclog"
	svkfwprotobuf "rest_api/api/framework"
	"rest_api/third_party"
)

/**
 * @var svk_logger
 * @brief Logger instance for gRPC logging.
 */
var svk_logger grpclog.LoggerV2

/*
 * @var certMutex
 * @brief Mutex for synchronizing access to certificate files. Multiple files (key and cert) are getting
 *	modified as part of update_certificate call. If any TLS session is getting established with a new connection,
 *	then it can fail because of inconsistency. This mutex protects the access to the files.
 */
var certMutex sync.Mutex

var (
	httpServer  *http.Server
	httpsServer *http.Server
	serverMu    sync.RWMutex
)

func InitServer() {
	serverMu.RLock()
	defer serverMu.RUnlock()
	httpServer = nil
	httpsServer = nil
}

/**
* @brief Returns the HTTP or HTTPS server instance based on the type.
* @param type Type of server. Can be one of "http" or "https"
* @return Returns the server instance or nil if invalid type given
 */
func GetServer(svc_type string) *http.Server {
	serverMu.RLock()
	defer serverMu.RUnlock()
	if svc_type == "http" {
		return httpServer
	} else if svc_type == "https" {
		return httpsServer
	}

	return nil
}

func SetServer(svc_type string, srv *http.Server) {
	serverMu.Lock()
	defer serverMu.Unlock()
	if svc_type == "http" {
		httpServer = srv
	} else if svc_type == "https" {
		httpsServer = srv
	}
}

/**
 * @brief Returns an HTTP handler for serving OpenAPI (Swagger) UI.
 *
 * @return http.Handler OpenAPI UI handler.
 */
func getOpenAPIHandler() http.Handler {
	mime.AddExtensionType(".svg", "image/svg+xml")
	subFS, err := fs.Sub(third_party.OpenAPI, "OpenAPI")
	if err != nil {
		panic("couldn't create sub filesystem: " + err.Error())
	}
	return http.FileServer(http.FS(subFS))
}

/**
 * @brief Reads configuration file for server settings.
 *
 * @param configFile Path to the configuration file.
 * @return httpServerEndpoint HTTP server endpoint.
 * @return httpsServerEndpoint HTTPS server endpoint.
 * @return controllerEndpoint Controller endpoint.
 */
func ReadConfigFileForServer(configFile string) (string, string, string) {
	var controllerEndpoint string
	var httpServerEndpoint string
	var httpsServerEndpoint string

	type Controller struct {
		Id   string `json:"id"`
		Port string `json:"port"`
	}
	type RestServer struct {
		Id        string `json:"id"`
		HTTPPort  string `json:"port"`
		HTTPSPort string `json:"https_port"`
	}

	fileContent, err := os.Open(configFile)
	if err != nil {
		log.Fatal(err)
		return "", "", ""
	}

	byteResult, _ := ioutil.ReadAll(fileContent)
	fileContent.Close()

	// Read the json file
	var sections map[string]json.RawMessage
	if err := json.Unmarshal(byteResult, &sections); err != nil {
		log.Fatal("failed to unmarshal config file")
	}

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
		controllerEndpoint = controller.Id + ":" + controller.Port
	} else {
		controllerEndpoint = ""
	}

	if len(restserver.Id) != 0 {
		if len(restserver.HTTPPort) != 0 {
			httpServerEndpoint = restserver.Id + ":" + restserver.HTTPPort
		}
		if len(restserver.HTTPSPort) != 0 {
			httpsServerEndpoint = restserver.Id + ":" + restserver.HTTPSPort
		} else {
			httpsServerEndpoint = restserver.Id + ":8443"
			svk_logger.Infof("https port is not configured. Using default value %s", httpsServerEndpoint)
		}
	} else {
		httpServerEndpoint = ""
		httpsServerEndpoint = ""
	}

	return httpServerEndpoint, httpsServerEndpoint, controllerEndpoint
}

/**
 * @brief Reads configuration file for logger settings.
 *
 * @param configFile Path to the configuration file.
 * @return logFileName Logger file name.
 */
func ReadConfigFileForLogger(configFile string) string {
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

/*
*
  - @brief This function parses the HTTP request for multipart form format.
    Reads the data of the entries "certificate_pem_file" and "key_pem_file" and
    saves the data into the /etc/svk/certificates folder as cert.pem and key.pem respectively.
    *
  - @param certFile Path to the certificate file.
  - @param keyFile Path to the key file.
  - @return http.HandlerFunc HTTP handler function with error or success status code.
*/
func updateCertificatesHandler(certFile *string, keyFile *string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		server := GetServer("https")
		svk_logger.Infof("updateCertificatesHandler: Server object address: %p", server)

		if r.Method != http.MethodPost {
			http.Error(w, "Invalid request method", http.StatusBadRequest)
			return
		}

		err := r.ParseMultipartForm(10 << 20) // 10 MB
		if err != nil {
			http.Error(w, "Failed to parse form", http.StatusBadRequest)
			return
		}

		svk_logger.Info("Retrieving certificate and key PEM files from multipartform")
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
		svk_logger.Info("Retrieved certificate and key PEM files from multipartform")

		// Read the files into bytes
		certBytes, err := io.ReadAll(cert)
		if err != nil {
			http.Error(w, "Failed to read certificate file from multipartform", http.StatusInternalServerError)
			return
		}

		keyBytes, err := io.ReadAll(key)
		if err != nil {
			http.Error(w, "Failed to read key file from multipartform", http.StatusInternalServerError)
			return
		}
		// Load TLS certificates to validate the cert
		_, err = tls.X509KeyPair(certBytes, keyBytes)
		if err != nil {
			svk_logger.Errorf("Failed to load TLS certificates: %v", err)
			http.Error(w, "Failed to load TLS certificates from multipartform", http.StatusInternalServerError)
			return
		}

		// All the validation done. Do mutex lock for saving the data so that the certificate
		// doesn't get generated when the multiple files save is in progress
		certMutex.Lock()
		defer certMutex.Unlock()

		// Save the uploaded files
		svk_logger.Info("Saving certificate and key files to local system")
		svk_logger.Infof("Saving certificate file to %s", *certFile)
		err = saveFile(*certFile, certBytes)
		if err != nil {
			http.Error(w, "Failed to save certificate file", http.StatusInternalServerError)
			return
		}

		svk_logger.Infof("Saving key file to %s", *keyFile)
		err = saveFile(*keyFile, keyBytes)
		if err != nil {
			http.Error(w, "Failed to save key file", http.StatusInternalServerError)
			os.Remove(*certFile)
			return
		}
		svk_logger.Info("Saved certificate and key files to local system")

		w.WriteHeader(http.StatusOK)
		if server == nil {
			svk_logger.Info("Certificates created successfully")
			w.Write([]byte("Certificates created successfully. Requires a REST server restart to take effect\n"))
		} else {
			svk_logger.Infof("TLSConfig: %+v", server.TLSConfig)
			svk_logger.Info("Certificates updated successfully")
			w.Write([]byte("Certificates updated successfully. Use the new certificate to access the HTTPS server\n"))
		}
	}
}

/**
 * @brief Saves a file to disk.
 *
 * @param filename File name.
 * @param fileData File data.
 * @return error Error if saving fails.
 */
func saveFile(filename string, fileData []byte) error {
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

	_, err = out.Write(fileData)
	svk_logger.Infof("Writing the data to file %s", filename)

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

/**
 * @brief Creates a TLS configuration for the HTTPS server.
 *
 * @param server HTTP server instance.
 * @param certFile Path to the certificate file.
 * @param keyFile Path to the key file.
 * @return error Error if creating TLS config fails.
 */
func createTLSServer(server *http.Server, certFile string, keyFile string) error {
	certMutex.Lock()
	defer certMutex.Unlock()

	svk_logger.Info("Creating TLS config for the HTTPS server")
	// Load TLS certificates to validate the cert
	_, err := tls.LoadX509KeyPair(certFile, keyFile)
	if err != nil {
		svk_logger.Error("Failed to load TLS certificates: %v", err)
		return err
	}

	// Create a TLS configuration
	tlsConfig := &tls.Config{
		GetCertificate: func(*tls.ClientHelloInfo) (*tls.Certificate, error) {
			cert, err := tls.LoadX509KeyPair(certFile, keyFile)
			return &cert, err
		},
		MinVersion: tls.VersionTLS12, // Minimum TLS version
	}

	// Create an HTTPS server
	server.TLSConfig = tlsConfig
	svk_logger.Info("TLS Config updated for HTTPS server")
	return nil
}

/**
 * @brief Returns an HTTP handler for routing requests.
 *
 * @param mux gRPC gateway serve mux.
 * @param oa OpenAPI handler.
 * @param certFile Path to the certificate file.
 * @param keyFile Path to the key file.
 * @return http.Handler HTTP handler.
 */
func requestHandler(mux *runtime.ServeMux, oa http.Handler, certFile, keyFile *string) http.Handler {
	newServeMux := http.NewServeMux()
	newServeMux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {

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
			updateCertificatesHandler(certFile, keyFile)(w, r)
			return
		}
		oa.ServeHTTP(w, r)
	})
	return newServeMux
}

/**
 * @brief Initializes the HTTP REST server.
 *
 * @param httpServerEndpoint HTTP server endpoint to service the HTTP requests.
 * @param controllerEndpoint Controller endpoint to send the request from HTTP to the Controller.
 * @param ctx gRPC Context.
 * @return *http.Server HTTP server instance.
 * @return error Error if initialization fails.
 */
func InitHTTPRestServer(httpServerEndpoint string, controllerEndpoint string, ctx context.Context, certFile string, keyFile string) (*http.Server, error) {

	// creating mux for gRPC gateway. This will multiplex or route request different gRPC service
	mux := runtime.NewServeMux()

	// setting up a dial up for gRPC service by specifying endpoint/target url
	err := svkfwprotobuf.RegisterControllerHandlerFromEndpoint(ctx, mux, controllerEndpoint, []grpc.DialOption{grpc.WithInsecure()})
	if err != nil {
		svk_logger.Fatal(err)
	}

	oa := getOpenAPIHandler()
	httpServer := &http.Server{
		Addr:    httpServerEndpoint,
		Handler: requestHandler(mux, oa, &certFile, &keyFile),
	}

	svk_logger.Info("Serving gRPC-Gateway and OpenAPI Documentation on http://", httpServerEndpoint)
	SetServer("http", httpServer)

	return httpServer, nil
}

/**
 * @brief Initializes the HTTPS REST server.
 *
 * @param httpsServerEndpoint HTTPS server endpoint to service the HTTPS requests.
 * @param controllerEndpoint Controller endpoint to send the request from HTTP to the Controller.
 * @param ctx gRPC Context.
 * @param certFile Path to the certificate file.
 * @param keyFile Path to the key file.
 * @return *http.Server HTTPS server instance.
 * @return error Error if initialization fails.
 */
func InitHTTPSRestServer(httpsServerEndpoint string, controllerEndpoint string, ctx context.Context, certFile string, keyFile string) (*http.Server, error) {
	if !fileExists(certFile) || !fileExists(keyFile) {
		return nil, nil
	}

	// creating mux for gRPC gateway. This will multiplex or route request different gRPC service
	mux := runtime.NewServeMux()

	// setting up a dial up for gRPC service by specifying endpoint/target url
	err := svkfwprotobuf.RegisterControllerHandlerFromEndpoint(ctx, mux, controllerEndpoint, []grpc.DialOption{grpc.WithInsecure()})
	if err != nil {
		svk_logger.Fatal(err)
	}

	oa := getOpenAPIHandler()

	svk_logger.Info("Creating HTTPS server configuration")
	httpsServer := &http.Server{
		Addr:    httpsServerEndpoint,
		Handler: requestHandler(mux, oa, &certFile, &keyFile),
	}
	err = createTLSServer(httpsServer, certFile, keyFile)
	if err != nil {
		svk_logger.Error("Failed in creating HTTPS server configuration")
		return nil, err
	}
	svk_logger.Info("Creating HTTPS server configuration succeeded")

	SetServer("https", httpsServer)
	svk_logger.Info("Serving gRPC-Gateway and OpenAPI Documentation on http://", httpsServer.Addr)

	return httpsServer, nil
}

/**
 * @brief Starts the REST server instance.
 *
 * @param server HTTP server instance.
 * @param useTLS Whether to start in HTTPS or HTTP.
 */
func RunRestServer(server *http.Server, useTLS bool) {

	var err error
	logMessage := "Starting the server to serve new connections on gRPC-Gateway in "
	logMessage += map[bool]string{true: "HTTPS", false: "HTTP"}[useTLS] + " mode"
	svk_logger.Info(logMessage)

	if useTLS {
		err = server.ListenAndServeTLS("", "")
	} else {
		err = server.ListenAndServe()
	}
	if !errors.Is(err, http.ErrServerClosed) {
		svk_logger.Fatalf("gRPC-Gateway server error: %v", err)
	}

	logMessage = "Stopped the gRPC-Gateway in "
	logMessage += map[bool]string{true: "HTTPS", false: "HTTP"}[useTLS] + " mode"
	svk_logger.Info(logMessage)
}

/**
 * @brief Initializes signal handling for the REST server.
 *
 * @param restServerChannel Channel for sending PID.
 * @return int PID of the process.
 */
func InitSignalHandler(restServerChannel chan<- int) int {

	pid := os.Getpid()
	select {
	case restServerChannel <- pid:
		// message sent
		svk_logger.Info("Sent the PID to the server channel ", pid)
	default:
		// message dropped
		svk_logger.Error("Couldn't send the PID to the server channel")
	}
	return pid
}

/**
 * @brief Stops the REST API servers depending on the server instances passed as args.
 *
 * @param ctx Context.
 * @return int Return code.
 */
func StopRestServer(ctx context.Context) int {
	ret := -1

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	s := <-sigChan

	svk_logger.Info("Received signal to the server -> ", s)

	httpServer = GetServer("http")
	if httpServer != nil {
		shutdownCtx, shutdownRelease := context.WithTimeout(ctx, 10*time.Second)
		defer shutdownRelease()
		if err := httpServer.Shutdown(shutdownCtx); err != nil {
			svk_logger.Fatalf("gRPC-Gateway HTTP server shutdown error: %v", err)
		} else {
			svk_logger.Info("Graceful gRPC-Gateway HTTP server shutdown complete.")
			ret = 0
		}
	}

	httpsServer = GetServer("https")
	if httpsServer != nil {
		shutdownCtx, shutdownRelease := context.WithTimeout(ctx, 10*time.Second)
		defer shutdownRelease()
		if err := httpsServer.Shutdown(shutdownCtx); err != nil {
			svk_logger.Fatalf("gRPC-Gateway HTTPS server shutdown error: %v", err)
		} else {
			svk_logger.Info("Graceful gRPC-Gateway HTTPS server shutdown complete.")
			ret = 0
		}
	}

	return ret
}

func fileExists(filename string) bool {
	_, err := os.Stat(filename)
	return err == nil
}

/**
 * @brief Initializes the logger.
 *
 * @param logFileName Logger file name.
 * @return *os.File Logger file handle.
 */
func InitLogger(logFileName string) *os.File {
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

	svk_logger = grpclog.NewLoggerV2(logFileHandle, logFileHandle, logFileHandle)
	grpclog.SetLoggerV2(svk_logger)
	svk_logger.Infof("Initialized the logger to the file %s", logFileName)
	return logFileHandle
}

func CloseLogger(logFileHandle *os.File) {
	svk_logger.Info("Closing the logger")
	logFileHandle.Close()
}

func InitRestServerFlags() {
	flag.String("httpServerEndpoint", "localhost:8001", "REST API HTTP server endpoint")
	flag.String("httpsServerEndpoint", "localhost:8443", "REST API HTTPS server endpoint")
	flag.String("grpc_controller_server", "localhost:9999", "gRPC Controller server endpoint")
	flag.String("config_file", "/usr/local/svk/conf.json", "Configuration file to read controller and server details")
	flag.String("cert_file", "/etc/svk/certificates/cert.pem", "TLS certificate file")
	flag.String("key_file", "/etc/svk/certificates/key.pem", "TLS key file")
}

/**
 * @brief Function to initialize the REST API server with context. The context can be used to cancel to stop the servers
 *
 * @param ctx Context.
 */
func MainWithContext(ctx context.Context) {
	defaultHttpServerEndpoint := flag.Lookup("httpServerEndpoint").Value.String()
	defaultHttpsServerEndpoint := flag.Lookup("httpsServerEndpoint").Value.String()
	defaultControllerEndpoint := flag.Lookup("grpc_controller_server").Value.String()
	configFile := flag.Lookup("config_file").Value.String()
	certFile := flag.Lookup("cert_file").Value.String()
	keyFile := flag.Lookup("key_file").Value.String()

	useTLS := false
	var httpServer *http.Server
	var httpsServer *http.Server
	var err error

	// Create Logger
	logFileName := ReadConfigFileForLogger(configFile)
	logFileHandle := InitLogger(logFileName)
	defer logFileHandle.Close()

	httpServerEndpoint, httpsServerEndpoint, controllerEndpoint := ReadConfigFileForServer(configFile)
	restServerChannel := make(chan int, 2)

	// If the entries are not present in controller section, override
	// with the default values or the command line value
	if len(controllerEndpoint) == 0 {
		controllerEndpoint = defaultControllerEndpoint
	}

	if len(httpServerEndpoint) == 0 {
		httpServerEndpoint = defaultHttpServerEndpoint
	}
	if len(httpsServerEndpoint) == 0 {
		httpsServerEndpoint = defaultHttpsServerEndpoint
	}

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	InitServer()
	InitSignalHandler(restServerChannel)

	httpServer, err = InitHTTPRestServer(httpServerEndpoint, controllerEndpoint, ctx, certFile, keyFile)
	if err != nil {
		svk_logger.Fatal(err)
	}
	go RunRestServer(httpServer, false)

	// Check the certificate files and run in HTTP/HTTPS mode
	if fileExists(certFile) && fileExists(keyFile) {
		svk_logger.Info("TLS key and cert files exist. Running the HTTPS mode as well")
		useTLS = true
	}

	if useTLS {
		httpsServer, err = InitHTTPSRestServer(httpsServerEndpoint, controllerEndpoint, ctx, certFile, keyFile)
		if err != nil {
			svk_logger.Fatal(err)
		}
		go RunRestServer(httpsServer, useTLS)
	}

	StopRestServer(ctx)
	close(restServerChannel)
	CloseLogger(logFileHandle)
}

/**
 * @brief Main entry point for the REST API server.
 */

func main() {
	// Separate the flag parsing outside the main function so that the UTs when called multiple times
	// under the same context will throw error "flag redefined"
	InitRestServerFlags()
	flag.Parse()

	MainWithContext(context.Background())
}
