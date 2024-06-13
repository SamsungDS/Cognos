package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"io/fs"
	"io/ioutil"
	"log"
	"mime"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	svkfwprotobuf "rest_api/api/framework"
	"rest_api/third_party"
	"github.com/grpc-ecosystem/grpc-gateway/v2/runtime"
	"google.golang.org/grpc"
	"google.golang.org/grpc/grpclog"
)

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

	type Controller struct{
		Id string `json:"id"`
		Port string `json:"port"`
	}
	type RestServer struct{
		Id string `json:"id"`
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
	} else{
		controllerId = ""
	}

	if len(restserver.Id) != 0 {
		restServerId = restserver.Id + ":" + restserver.Port
	} else{
		restServerId = ""
	}

	return restServerId, controllerId
}

func readConfigFileForLogger(configFile string) (string) {
	type Logger struct{
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

func InitRestServer(restServerId string, controllerId string, ctx context.Context, log grpclog.LoggerV2) (*http.Server) {
	var server *http.Server;

	// creating mux for gRPC gateway. This will multiplex or route request different gRPC service
	mux := runtime.NewServeMux()

	// setting up a dial up for gRPC service by specifying endpoint/target url
	err := svkfwprotobuf.RegisterControllerHandlerFromEndpoint(ctx, mux, controllerId, []grpc.DialOption{grpc.WithInsecure()})
	if err != nil {
		log.Fatal(err)
	}

	oa := getOpenAPIHandler()
	server = &http.Server{
		Addr: restServerId,
		Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if strings.HasPrefix(r.URL.Path, "/api") {
				mux.ServeHTTP(w, r)
				return
			}
			oa.ServeHTTP(w, r)
		}),
	}
	log.Info("Serving gRPC-Gateway and OpenAPI Documentation on http://", restServerId)
	return server
}

func RunRestServer(server *http.Server, log grpclog.LoggerV2, restServerChannel chan<- int) int {

	pid := os.Getpid()
	select {
		case restServerChannel <- pid:
			// message sent
			log.Info("Sent the PID to the server channel")
		default:
			// message dropped
			log.Error("Couldn't send the PID to the server channel")
	}
	log.Info("Started serving new connections on gRPC-Gateway.")
	if err := server.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		log.Fatalf("gRPC-Gateway server error: %v", err)
	}
	log.Info("Stopped serving new connections on gRPC-Gateway.")

	return pid
}

func StopRestServer(server *http.Server, ctx context.Context, log grpclog.LoggerV2) int {
	ret := -1

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	s := <- sigChan

	log.Info("Received signal to the server -> ", s)

    shutdownCtx, shutdownRelease := context.WithTimeout(ctx, 10*time.Second)
    defer shutdownRelease()

    if err := server.Shutdown(shutdownCtx); err != nil {
        log.Fatalf("gRPC-Gateway server shutdown error: %v", err)
    } else {
		log.Info("Graceful gRPC-Gateway server shutdown complete.")
		ret = 0
	}

	return ret
}

func main() {
	grpcServerEndpoint := flag.String("grpc-server-endpoint",  "localhost:8001", "gRPC server endpoint")
	grpcControllerServer := flag.String("grpc-controller-server",  "localhost:9999", "gRPC Controller server endpoint")
	configFile := flag.String("config-file",  "/usr/local/svk/conf.json", "Configuration file to read controller and server details")

	flag.Parse()

	restServerId, controllerId := readConfigFileForServer(*configFile)
	logFileName := readConfigFileForLogger(*configFile)
	restServerChannel := make(chan int, 2)

	if len(logFileName) == 0 {
		logFileName = "/var/log/svk/svk_mgmt_rest_api.log"
	}

	logFileHandle, err := os.Create(logFileName)
    if err != nil {
        log.Fatalf("Failed to create logger file: %v", logFileName)
    }

	log := grpclog.NewLoggerV2(logFileHandle, ioutil.Discard, ioutil.Discard)
	grpclog.SetLoggerV2(log)

	// If the entries are not present in controller section, override
	// with the default values or the command line value
	if len(controllerId) == 0 {
		controllerId = *grpcControllerServer
	}

	if len(restServerId) == 0 {
		restServerId = *grpcServerEndpoint
	}

	ctx := context.Background()
	server := InitRestServer(restServerId, controllerId, ctx, log)
	go RunRestServer(server, log, restServerChannel)

	StopRestServer(server, ctx, log)
	close(restServerChannel)
}
