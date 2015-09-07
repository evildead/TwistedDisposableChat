WHAT IS TWISTED "DISPOSABLE CHAT"

Twisted "Disposable Chat"
A simple chat built with the Twisted Python protocol.
It enables the broadcasting of messages and the communication user-to-user.
It enables a multi-node deploy of the chat server by using the redis caching and message broker mechanisms
||-------------------------------------------------------------------------------------------------------------------||


HOW CAN I USE IT

You need an active redis server

To start the twisted chat server:
open a terminal,
go to the code folder,
type: dispochat.py

A demon implementing the websocket protocol will start listening to port 9000

Use the javascript/html5 client named index.html written with Bootstrap and Jquery
||-------------------------------------------------------------------------------------------------------------------||


FIXES AND NEXT STEPS

Fix:
- handle redis failures
- handle deferreds failures

Next steps:
- add a load balancer with txLoadBalancer
||-------------------------------------------------------------------------------------------------------------------||

