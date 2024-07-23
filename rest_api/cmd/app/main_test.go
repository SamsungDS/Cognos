package main

import (
	"context"
	"io/ioutil"
	"os"
	"os/exec"
	"syscall"
	"testing"
	"time"
	"google.golang.org/grpc/grpclog"
)

func TestConfigFile(t *testing.T) {
	t.Logf("Running TestConfigFile")
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

func TestInitRestServer(t *testing.T){
	t.Logf("Running TestInitRestServer")
	log := grpclog.NewLoggerV2(os.Stdout, ioutil.Discard, ioutil.Discard)
	grpclog.SetLoggerV2(log)
	ctx := context.Background()
	server := InitRestServer("localhost:8001", "localhost:9999", ctx, log)
	if server == nil {
		t.Fatalf("Error in creating RestServer server interface")
	}
}

func IssueSignal(restServerChannel <-chan int) int {
	pid:= <- restServerChannel

	time.Sleep(10 * time.Second)

	proc, err := os.FindProcess(pid)
	if err != nil {
		return -1
	}
	proc.Signal(syscall.SIGINT)
	return 0
}

func TestRunRestServer(t *testing.T){
	t.Logf("Running TestRunRestServer")
	log := grpclog.NewLoggerV2(os.Stdout, ioutil.Discard, ioutil.Discard)
	restServerChannel := make(chan int, 2)
	grpclog.SetLoggerV2(log)
	ctx := context.Background()
	server := InitRestServer("localhost:8001", "localhost:9999", ctx, log)
	if server == nil {
		t.Fatalf("Error in creating RestServer server interface")
	}
	go RunRestServer(server, log, restServerChannel)
	go IssueSignal(restServerChannel)
	StopRestServer(server, ctx, log)
	close(restServerChannel)
}

func TestMain(t *testing.T){
 	go main()
 	time.Sleep(5 * time.Second)

	cmd := "kill -INT $(netstat -anp|grep 8001|awk '{print $NF}'|sed 's;/; ;g'|awk '{print $1}')"
	out, err := exec.Command("bash", "-c", cmd).Output()
	if err != nil {
		t.Fatalf("Error in sending the signal to the process %v", err)
	}
	if len(out) != 0 {
		t.Logf("Output %s", out)
	}
}
