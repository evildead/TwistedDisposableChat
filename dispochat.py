###############################################################################
#
# The MIT License (MIT)
#
# Copyright (c) Tavendo GmbH
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
###############################################################################

import sys
import random
import json
import txredisapi as redis
from twisted.internet import reactor
from twisted.python import log
from twisted.web.server import Site
from twisted.web.static import File
from twisted.internet import defer

from autobahn.twisted.websocket import WebSocketServerFactory, WebSocketServerProtocol, listenWS


WEBSERVICE_LISTENING_PORT = 9000
WEBSERVER_LISTENING_PORT = 8080
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_CLIENTS_KEY_PREFIX = 'twistedchatclients'
REDIS_CHANNEL_MESSAGES = 'twistedchatmessages'
REDIS_CHANNEL_BROADCASTMSG_ID = 0
REDIS_CHANNEL_DIRECTMSG_ID = 1
REDIS_CHANNEL_OTHEROP_ID = 2
REDIS_CLIENT_TIMETOLIVE = 60
TWISTEDCHAT_POLL_TIME = 50

def fromconfigfilepathtoglobalserverparams(configfilepath):
    with open(configfilepath, 'r') as content_file:
        configfilecontent = content_file.read()
        configfilecontent.decode('utf8')
        jsondecodedconfigfilecontent = json.loads(configfilecontent, encoding='utf8')
        if 'wsport' in jsondecodedconfigfilecontent:
            global WEBSERVICE_LISTENING_PORT
            WEBSERVICE_LISTENING_PORT = jsondecodedconfigfilecontent['wsport']
        if 'redis_host' in jsondecodedconfigfilecontent:
            global REDIS_HOST
            REDIS_HOST = jsondecodedconfigfilecontent['redis_host']
        if 'redis_port' in jsondecodedconfigfilecontent:
            global REDIS_PORT
            REDIS_PORT = jsondecodedconfigfilecontent['redis_port']
        if 'redisclient_ttl' in jsondecodedconfigfilecontent:
            global REDIS_CLIENT_TIMETOLIVE
            REDIS_CLIENT_TIMETOLIVE = jsondecodedconfigfilecontent['redisclient_ttl']
        if 'chat_pollingtime' in jsondecodedconfigfilecontent:
            global TWISTEDCHAT_POLL_TIME
            TWISTEDCHAT_POLL_TIME = jsondecodedconfigfilecontent['chat_pollingtime']
        if 'redis_clients_key_prefix' in jsondecodedconfigfilecontent:
            global REDIS_CLIENTS_KEY_PREFIX
            REDIS_CLIENTS_KEY_PREFIX = jsondecodedconfigfilecontent['redis_clients_key_prefix']
        if 'redis_channel_messages' in jsondecodedconfigfilecontent:
            global REDIS_CHANNEL_MESSAGES
            REDIS_CHANNEL_MESSAGES = jsondecodedconfigfilecontent['redis_channel_messages']


class TwistedChatServerProtocol(WebSocketServerProtocol):
    def __init__(self):
        WebSocketServerProtocol.__init__(self)
        self.name = None
        self.key = -1

    def onOpen(self):
        self.factory.register(self)

    @defer.inlineCallbacks
    def onMessage(self, payload, isBinary):
        #it's the request
        payload.decode('utf8')
        jsondecodedpayload = json.loads(payload, encoding='utf8')
        if not isBinary:
            if jsondecodedpayload['eventtype'] == 'txt':
                # private text message
                clientkey = jsondecodedpayload['toclientkey']
                if self.factory.checkclientinlist(clientkey):
                    self.factory.sendtoclient(clientkey, payload)
                else:
                    #redisconn = yield redis.Connection(REDIS_HOST, REDIS_PORT)
                    twistedchannel = REDIS_CHANNEL_MESSAGES + "." + str(REDIS_CHANNEL_DIRECTMSG_ID)
                    yield redisconn.publish(twistedchannel, payload)
            elif jsondecodedpayload['eventtype'] == 'btxt':
                # broadcast text message
                #self.factory.broadcast(payload)
                #redisconn = yield redis.Connection(REDIS_HOST, REDIS_PORT)
                twistedchannel = REDIS_CHANNEL_MESSAGES + "." + str(REDIS_CHANNEL_BROADCASTMSG_ID)
                yield redisconn.publish(twistedchannel, payload)
            elif jsondecodedpayload['eventtype'] == 'getclist':
                # get list of clients message request
                clientkey = jsondecodedpayload['fromclientkey']
                self.factory.sendclientlisttoclient(clientkey)
            elif jsondecodedpayload['eventtype'] == 'getidentity':
                # get the identity request message
                clientkey = jsondecodedpayload['fromclientkey']
                self.factory.sendidentitytoclient(clientkey)

        else:
            pass

    def connectionLost(self, reason):
        WebSocketServerProtocol.connectionLost(self, reason)
        self.factory.unregister(self)


class TwistedChatServerFactory(WebSocketServerFactory):

    """
    Register new clients
    Broadcast messages
    Send private messages
    Unregister close connections
    """

    def __init__(self, url, debug=False, debugCodePaths=False):
        WebSocketServerFactory.__init__(self, url, debug=debug, debugCodePaths=debugCodePaths)
        self.clients = {}
        self.clientnames = {}
        self.pollingprocedure()
        #self.cleanclientsfromredis()

    @defer.inlineCallbacks
    def pollingprocedure(self):
        # refresh redis keys for connected clients
        yield self.refreshredisconnectedclients()
        # send the client list in broadcast
        yield self.broadcastclientlist()
        reactor.callLater(TWISTEDCHAT_POLL_TIME, self.pollingprocedure)

    @defer.inlineCallbacks
    def register(self, client):
        if client not in self.clients.values():
            clientkey = random.randint(1, 2000000000)
            clientname = 'guest_' + str(clientkey)
            self.clients[clientkey] = client
            self.clientnames[clientkey] = clientname
            client.key = clientkey
            client.name = clientname
            log.msg("registered client(id, name): (" + str(clientkey) + ", " + clientname + ")")

            # send the identity to the new registered client
            self.sendidentitytoclient(clientkey)

            # connect to redis host to handle cached parameters
            #redisconn = yield redis.Connection(REDIS_HOST, REDIS_PORT)
            newclientkey = REDIS_CLIENTS_KEY_PREFIX + "_" + str(clientkey)
            yield redisconn.set(newclientkey, clientname, expire=REDIS_CLIENT_TIMETOLIVE)

            # publish the "broadcast client list" to all the nodes
            yield self.redispublishbroadcastclientlist()

    @defer.inlineCallbacks
    def unregister(self, client):
        if client in self.clients.values():
            self.clients.pop(client.key)
            self.clientnames.pop(client.key)
            log.msg("unregistered client {}".format(client.name))

            #redisconn = yield redis.Connection(REDIS_HOST, REDIS_PORT)
            oldclientkey = REDIS_CLIENTS_KEY_PREFIX + "_" + str(client.key)
            yield redisconn.delete(oldclientkey)

            # publish the "broadcast client list" to all the nodes
            yield self.redispublishbroadcastclientlist()

    @defer.inlineCallbacks
    def getclientsdictfromredis(self):
        #redisconn = yield redis.Connection(REDIS_HOST, REDIS_PORT)
        clientkeypattern = REDIS_CLIENTS_KEY_PREFIX + "_*"
        clientskeys = yield redisconn.keys(clientkeypattern)
        dicttoreturn = {}
        for k in clientskeys:
            tmpVal = yield redisconn.get(k)
            splittedkey = k.split("_")
            if len(splittedkey) > 1:
                myclientkey = int(splittedkey[1])
                dicttoreturn[myclientkey] = tmpVal
        defer.returnValue(dicttoreturn)

    @defer.inlineCallbacks
    def cleanclientsfromredis(self):
        #redisconn = yield redis.Connection(REDIS_HOST, REDIS_PORT)
        clientskeys = []
        for ckey in self.clients:
            tmpkey = REDIS_CLIENTS_KEY_PREFIX + "_" + str(ckey)
            clientskeys.push(tmpkey)
        #clientskeys = yield redisconn.hkeys(REDIS_HASH_CLIENT_KEY)
        if clientskeys:
            yield redisconn.delete(clientskeys)

    def broadcast(self, msg):
        log.msg("broadcasting message: " + msg + ",||,and its type is: " + str(type(msg)))
        for (ckey, c) in self.clients.items():
            c.sendMessage(msg)
            log.msg("message sent to {}".format(self.clientnames[ckey]))

    @defer.inlineCallbacks
    def broadcastclientlist(self):
        log.msg("broadcasting client list")
        redisclientsdict = yield self.getclientsdictfromredis()
        myclientlistmsg = MsgPayload()
        myclientlistmsg.eventtype = 'clist'
        #myclientlistmsg.clientlist = self.clientnames
        myclientlistmsg.clientlist = redisclientsdict
        msg = json.dumps(myclientlistmsg.__dict__)
        for (ckey, c) in self.clients.items():
            c.sendMessage(msg)
            log.msg("client list sent to {}".format(self.clientnames[ckey]))

    def sendtoclient(self, clientkey, msg):
        if clientkey in self.clients:
            myclient = self.clients[clientkey]
            myclient.sendMessage(msg)

    def sendidentitytoclient(self, clientkey):
        if clientkey in self.clients:
            myclient = self.clients[clientkey]
            myidentitymsg = MsgPayload()
            myidentitymsg.eventtype = 'identity'
            identityDict = {}
            identityDict['key'] = clientkey
            identityDict['name'] = self.clientnames[clientkey]
            myidentitymsg.identity = identityDict
            msg = json.dumps(myidentitymsg.__dict__)
            myclient.sendMessage(msg)

    @defer.inlineCallbacks
    def sendclientlisttoclient(self, clientkey):
        if clientkey in self.clients:
            myclient = self.clients[clientkey]
            redisclientsdict = yield self.getclientsdictfromredis()
            myclientlistmsg = MsgPayload()
            myclientlistmsg.eventtype = 'clist'
            #myclientlistmsg.clientlist = self.clientnames
            myclientlistmsg.clientlist = redisclientsdict
            msg = json.dumps(myclientlistmsg.__dict__)
            myclient.sendMessage(msg)

    def checkclientinlist(self, clientkey):
        if clientkey in self.clients:
            return True
        else:
            return False

    @defer.inlineCallbacks
    def refreshredisconnectedclients(self):
        #redisconn = yield redis.Connection(REDIS_HOST, REDIS_PORT)
        for ckey in self.clients:
            tmpkey = REDIS_CLIENTS_KEY_PREFIX + "_" + str(ckey)
            clientname = self.clientnames[ckey]
            yield redisconn.set(tmpkey, clientname, expire=REDIS_CLIENT_TIMETOLIVE)

    @defer.inlineCallbacks
    def redispublishbroadcastclientlist(self):
        #redisconn = yield redis.Connection(REDIS_HOST, REDIS_PORT)
        twistedchannel = REDIS_CHANNEL_MESSAGES + "." + str(REDIS_CHANNEL_OTHEROP_ID)
        payload = 'broadcastclientlist'
        yield redisconn.publish(twistedchannel, payload)

class MsgPayload:
    def __init__(self):
        self.eventtype = None
        self.msgcontent = None


class myRedisProtocol(redis.SubscriberProtocol):
    def connectionMade(self):
        self.twistedchatfactory = factory
        log.msg("waiting for messages...")
        log.msg("use the redis client to send messages:")
        #log.msg("$ redis-cli publish zz test")
        log.msg("$ redis-cli publish " + REDIS_CHANNEL_MESSAGES + ".6253472 \"hello world\"")

        #self.auth("foobared")

        #self.subscribe("zz")
        self.psubscribe(REDIS_CHANNEL_MESSAGES + ".*")
        # reactor.callLater(10, self.unsubscribe, "zz")
        # reactor.callLater(15, self.punsubscribe, "foo.*")

        # self.continueTrying = False
        # self.transport.loseConnection()

    def messageReceived(self, pattern, channel, message):
        # check channel name after dot ("messages.xxxx") and call the TwistedChatServerFactory broadcast method if xxxx < 1,
        # or the method sendtoclient if xxxx is in TwistedChatServerFactory's clients dict
        log.msg("pattern=%s, channel=%s message=%s" % (pattern, channel, message))
        channelchunks = channel.split('.')
        if len(channelchunks) > 1:
            channelid = int(channelchunks[1])
            # direct message to a single client
            if channelid == REDIS_CHANNEL_DIRECTMSG_ID:
                message = message.encode('utf-8')
                jsondecodedpayload = json.loads(message, encoding='utf8')
                clientid = jsondecodedpayload['toclientkey']
                # if clientid is not in the list, the message won't be sent
                self.twistedchatfactory.sendtoclient(clientid, message)
            # message to broadcast
            elif channelid == REDIS_CHANNEL_BROADCASTMSG_ID:
                message = message.encode('utf-8')
                self.twistedchatfactory.broadcast(message)
            # other operations
            elif channelid == REDIS_CHANNEL_OTHEROP_ID:
                if message == 'broadcastclientlist':
                    # send the client list in broadcast
                    self.twistedchatfactory.broadcastclientlist()

    def connectionLost(self, reason):
        log.msg("lost connection:", reason)


class myRedisFactory(redis.SubscriberFactory):
    # SubscriberFactory is a wapper for the ReconnectingClientFactory
    maxDelay = 120
    continueTrying = True
    protocol = myRedisProtocol


# THE MAIN
if __name__ == '__main__':

    debug = False
    if len(sys.argv) > 1:
        if sys.argv[1] == 'debug':
            log.startLogging(sys.stdout)
            debug = True
        elif sys.argv[1].startswith('wsport'):
            wsportplitted = sys.argv[1].split('=')
            if len(wsportplitted) > 1:
                WEBSERVICE_LISTENING_PORT = int(wsportplitted[1])
        elif sys.argv[1].startswith('configfile'):
            wsportplitted = sys.argv[1].split('=')
            if len(wsportplitted) > 1:
                configfilepath = wsportplitted[1]
                fromconfigfilepathtoglobalserverparams(configfilepath)

    # open connection with redis server to query for keys and publish to channels
    redisconn = redis.lazyConnectionPool(REDIS_HOST, REDIS_PORT)

    # do the webservice server by listening to incoming messages on port WEBSERVICE_LISTENING_PORT
    ServerFactory = TwistedChatServerFactory
    factory = ServerFactory("ws://localhost:" + str(WEBSERVICE_LISTENING_PORT), debug=debug, debugCodePaths=debug)
    factory.protocol = TwistedChatServerProtocol
    factory.setProtocolOptions(allowHixie76=True)
    listenWS(factory)

    # connect to redis host for the publish/subscribe protocol
    TwistedRedisFactory = myRedisFactory()
    reactor.connectTCP(REDIS_HOST, REDIS_PORT, TwistedRedisFactory)

    # do the http server by listening to incoming messages on port 8080
    #webdir = File(".")
    #web = Site(webdir)
    #reactor.listenTCP(WEBSERVER_LISTENING_PORT, web)

    reactor.run()
