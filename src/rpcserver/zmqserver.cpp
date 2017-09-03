/*
 * <one line to give the library's name and an idea of what it does.>
 * Copyright (C) 2017  Aetf <aetf@unlimitedcodeworks.xyz>
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 */

#include "zmqserver.h"

#include "rpcservercore.h"
#include "platform/logging.h"
#include "utils/protoutils.h"

#include "protos.h"

#include <functional>
#include <chrono>
#include <iostream>

using namespace std::literals::chrono_literals;

ZmqServer::ZmqServer(std::unique_ptr<RpcServerCore> &&logic)
    : m_zmqCtx(1)
    , m_keepRunning(false)
    , m_frontend_sock(m_zmqCtx, zmq::socket_type::router)
    , m_backend_sock(m_zmqCtx, zmq::socket_type::pair)
    , m_pLogic(std::move(logic))
    , m_sendQueue(128)
{
    m_frontend_sock.setsockopt(ZMQ_ROUTER_MANDATORY, 1);
    m_frontend_sock.setsockopt(ZMQ_ROUTER_HANDOVER, 1);
}

ZmqServer::~ZmqServer()
{
    requestStop();
}

void ZmqServer::start(const std::string& address)
{
    if (m_keepRunning) {
        ERR("ZmqServer already started.");
        return;
    }

    try {
        INFO("Binding frontend socket to address: {}", address);
        m_frontend_sock.bind(address);

        auto baddr = "inproc://backend";
        DEBUG("Binding backend socket to address: {}", baddr);
        m_backend_sock.bind(baddr);
    } catch (zmq::error_t &err) {
        FATAL("Error while binding sockets: {}", err);
        // re-throw to stop the process
        throw;
    }

    m_keepRunning = true;
    m_sendThread = std::make_unique<std::thread>(std::bind(&ZmqServer::sendLoop, this));

    // proxy and recving loop must be called in the same thread as constructor (because of fe and bd sockets)
    proxyRecvLoop();
}

bool ZmqServer::pollWithCheck(const std::vector<zmq::pollitem_t> &items, long timeout)
{
    try {
        zmq::poll(items, timeout);
    } catch (zmq::error_t &err) {
        switch (err.num()) {
        case ETIMEDOUT:
            return true;
        case EINTR:
        case ETERM:
            m_keepRunning = false;
            return false;
        default:
            ERR("Exiting serving due to error while polling: {}", err);
            m_keepRunning = false;
            return false;
        }
    }
    return true;
}

void ZmqServer::proxyRecvLoop()
{
    INFO("Started recving and sending loop");
    // set up pulling.
    // we are interested in POLLIN and POLLOUT on m_frontend_sock, and POLLIN out m_backend_sock.
    // messages received on m_frontend_sock are directly dispatched using m_pLogic,
    // messages received on m_backend_sock are forwarded to m_frontend_sock.

    static std::vector<zmq::pollitem_t> pollin_events {
        {m_frontend_sock, 0, ZMQ_POLLIN, 0},
        {m_backend_sock, 0, ZMQ_POLLIN, 0},
    };
    static std::vector<zmq::pollitem_t> all_events {
        {m_frontend_sock, 0, ZMQ_POLLIN | ZMQ_POLLOUT, 0},
        {m_backend_sock, 0, ZMQ_POLLIN, 0},
    };
    std::vector<zmq::pollitem_t> *wait_events = &pollin_events;

    bool canSendOut = false;
    bool needSendOut = false;
    bool shouldDispatch = false;
    while (m_keepRunning) {
        // first blocking wait on pollin (read) events
        TRACE("Blocking pool on {}", wait_events == &pollin_events ? "pollin events" : "all events");
        if (!pollWithCheck(*wait_events, -1)) {
            break;
        }
        // something happened, so we poll w/o waiting on all_events
        // to set events in all_events
        TRACE("Non-blocking poll on all events");
        if (!pollWithCheck(all_events, 0)) {
            break;
        }

        // process events
        for (auto item : all_events) {
            if (item.socket == m_frontend_sock) {
                shouldDispatch = (item.revents & ZMQ_POLLIN) != 0;
                canSendOut = (item.revents & ZMQ_POLLOUT) != 0;
            } else if (item.socket == m_backend_sock) {
                needSendOut = (item.revents & ZMQ_POLLIN) != 0;
            }
        }
        TRACE("Events summary: shouldDispatch={}, canSendOut={}, needSendOut={}",
              shouldDispatch, canSendOut, needSendOut);

        // process dispatch if any
        if (shouldDispatch) {
            dispatch(m_frontend_sock);
            shouldDispatch = false;
        }

        // forward any send message
        if (needSendOut && canSendOut) {
            TRACE("Forwarding message out");
            zmq::message_t msg;
            bool more = false;
            while (true) {
                try {
                    m_backend_sock.recv(&msg);
                    TRACE("Forwarding message part: {}", msg);
                    more = m_backend_sock.getsockopt<int64_t>(ZMQ_RCVMORE);
                    m_frontend_sock.send(msg, more ? ZMQ_SNDMORE : 0);
                    if (!more)
                        break;
                } catch (zmq::error_t &err) {
                    ERR("Dropping message part while sending out due to error: {}", err);
                    if (!more)
                        break;
                }
            }
            needSendOut = canSendOut = false;
            wait_events = &pollin_events;
        } else if (needSendOut) {
            // should also wait for POLLOUT on m_frontend_sock
            wait_events = &all_events;
        } else if (canSendOut) {
            // only wait for POLLIN on sockets
            wait_events = &pollin_events;
        }
    }
}

void ZmqServer::dispatch(zmq::socket_t &sock)
{
    MultiPartMessage identities;
    zmq::message_t evenlop;
    zmq::message_t body;
    try {
        TRACE("==============================================================");
        // First receive all identity frames added by ZMQ_ROUTER socket
        identities->emplace_back();
        sock.recv(&identities->back());
        TRACE("Received identity frame {}: {}", identities->size() - 1, identities->back());
        // Identity frames stop at an empty message
        // ZMQ_RCVMORE is a int64_t according to doc, not a bool
        while (identities->back().size() != 0 && sock.getsockopt<int64_t>(ZMQ_RCVMORE)) {
            identities->emplace_back();
            sock.recv(&identities->back());
            TRACE("Received identity frame {}: {}", identities->size() - 1, identities->back());
        }
        if (!sock.getsockopt<int64_t>(ZMQ_RCVMORE)) {
            ERR("Skipped one iteration due to no body message part found after identity frames");
            return;
        }
        // Now receive our message
        sock.recv(&evenlop);
        TRACE("Received evenlop frame: {}", evenlop);
        if (!sock.getsockopt<int64_t>(ZMQ_RCVMORE)) {
            ERR("Skipped one iteration due to no body message part found after identity frames");
            return;
        }
        // TODO: handle multi-part body, which is used by RecvTensorResponse
        // though it's doubtable if we will receive this on executor side.
        sock.recv(&body);
        TRACE("Received body frame: {}", body);
    } catch (zmq::error_t &err) {
        ERR("Skipped one iteration due to error while receiving: {}", err);
        return;
    }
    auto pEvenlop = utils::createMessage<executor::EvenlopDef>("executor.EvenlopDef",
                                                               evenlop.data(), evenlop.size());
    if (!pEvenlop) {
        ERR("Skipped one iteration due to malformatted request evenlop received.");
        return;
    }
    DEBUG("Received request evenlop: {}", *pEvenlop);

    // step 1. replace the first frame in identity with the requested identity and make a sender
    if (!pEvenlop->recvidentity().empty()) {
        identities->front().rebuild(pEvenlop->recvidentity().data(), pEvenlop->recvidentity().size());
    }
    auto sender = std::make_shared<SenderImpl>(*this, pEvenlop->seq(), std::move(identities));

    // step 2. create request object
    auto pRequest = utils::createMessage(pEvenlop->type(), body.data(), body.size());
    if (!pRequest) {
        ERR("Skipped one iteration due to malformatted request received.");
        return;
    }
    DEBUG("Received request body byte array size {}", body.size());

    // step 3. dispatch
    auto f = m_pLogic->dispatch(sender, *pEvenlop, *pRequest)

    // step 4. send response back
    .then([sender = std::move(sender)](ProtoPtr &&pResponse) mutable {
        if (pResponse) {
            sender->sendMessage(std::move(pResponse));
        }
    }).fail([](std::exception_ptr e){
        ERR("Caught exception in logic dispatch: {}", e);
    });
}

ZmqServer::SenderImpl::SenderImpl(ZmqServer &server, uint64_t seq, MultiPartMessage &&identities)
    : m_server(server)
    , m_identities(std::move(identities))
    , m_seq(seq)
{
}

void ZmqServer::SenderImpl::sendMessage(ProtoPtr &&msg)
{
    MultiPartMessage parts;
    parts->emplace_back(msg->ByteSizeLong());
    auto &reply = parts->back();
    msg->SerializeToArray(reply.data(), reply.size());
    sendMessage(msg->GetTypeName(), std::move(parts));
}

void ZmqServer::SenderImpl::sendMessage(const std::string &typeName, MultiPartMessage &&msg)
{
    auto parts = m_identities.clone();
    // step 4.1. unused parts of evenlop is unset to save a few bytes on the wire,
    executor::EvenlopDef evenlop;
    evenlop.set_seq(m_seq);
    evenlop.set_type(typeName);
    parts->emplace_back(evenlop.ByteSizeLong());
    evenlop.SerializeToArray(parts->back().data(), parts->back().size());

    // step 4.2. append actual message
    TRACE("Response proto object have size {} with evenlop {}", msg.totalSize(), evenlop);
    parts.merge(std::move(msg));

    m_server.sendMessage(std::move(parts));
}

uint64_t ZmqServer::SenderImpl::sequenceNumber() const
{
    return m_seq;
}

void ZmqServer::sendMessage(MultiPartMessage &&parts)
{
    m_sendQueue.push({parts.release()});
}

void ZmqServer::sendLoop()
{
    zmq::socket_t sock(m_zmqCtx, zmq::socket_type::pair);
    sock.connect(m_baddr);
    INFO("Sending loop started");

    while (m_keepRunning) {
        SendItem item;
        if(!m_sendQueue.pop(item)) {
            std::this_thread::sleep_for(1ms);
            continue;
        }
        // Wrap the address in smart pointer immediately so we won't risk memory leak.
        MultiPartMessage parts(item.p_parts);
        try {
            for (size_t i = 0; i != parts->size() - 1; ++i) {
                auto &msg = parts->at(i);
                sock.send(msg, ZMQ_SNDMORE);
            }
            sock.send(parts->back());
            TRACE("Response sent on internal socket");
        } catch (zmq::error_t &err) {
            ERR("Sending error: {}", err);
        }
    }
}

void ZmqServer::requestStop()
{
    if (!m_keepRunning) {
        return;
    }

    INFO("Stopping ZMQ context");
    m_keepRunning = false;
    m_zmqCtx.close();
}

void ZmqServer::join()
{
    if (m_sendThread && m_sendThread->joinable()) {
        m_sendThread->join();
    }
}
