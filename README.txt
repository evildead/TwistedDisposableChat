To start the chat server:
open a terminal,
go to the code folder,
type: danchat.py

Two demons will start:
1) the one listening to port 9000 that implements the websocket protocol,
2) (optional): a server web listening to port 8080, which root will be the current folder




Fix:
- gestire failure redis
- gestire failure dei deferred

Prossime aggiunte:
- aggiungere un load balancer tramite txLoadBalancer
