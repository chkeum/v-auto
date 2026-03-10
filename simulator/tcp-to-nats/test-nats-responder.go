package main

import (
    "fmt"
    "log"
    "os"
    "os/signal"
    "syscall"
    "github.com/nats-io/nats.go"
)

func main() {
    nc, err := nats.Connect("nats://localhost:4222")
    if err != nil {
        log.Fatal(err)
    }
    defer nc.Close()
    
    fmt.Println("✅ Connected to NATS, subscribing to tcp.subs.change...")
    
    nc.Subscribe("tcp.subs.change", func(m *nats.Msg) {
        fmt.Printf("📨 Received: %s\n", string(m.Data))
        response := []byte(`{"status":"success","data":{"result":"processed"}}`)
        m.Respond(response)
        fmt.Printf("✅ Sent response\n")
    })
    
    fmt.Println("🎧 Listening for requests...")
    
    sig := make(chan os.Signal, 1)
    signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
    <-sig
    
    fmt.Println("\n👋 Shutting down...")
}
