/*
 * <one line to give the library's name and an idea of what it does.>
 * Copyright (C) 2018  Peifeng Yu <peifeng@umich.edu>
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
 */

#ifndef SALUS_OPLIB_TENSORFLOW_RENDEZVOUSMGR_H
#define SALUS_OPLIB_TENSORFLOW_RENDEZVOUSMGR_H

#include "oplibraries/tensorflow/tensorflow_headers.h"
#include "oplibraries/tensorflow/tfutils.h"
#include "utils/macros.h"
#include <mutex>
#include <string>
#include <unordered_map>

namespace salus::oplib::tensorflow {

// RendezvousMgr keeps track of a set of local rendezvous instances.
// All tensors sent by this worker are buffered in a RendezvousMgr
// until the tensor is received.  Each global unique "step_id"
// corresponds to one local rendezvous instance managed by a
// RendezvousMgr.
//
// E.g.,
//   Rendezvous* rendez = worker_env->rendezvous_mgr->Find(0x8935);
//   fork execution of an graph executor using "rendez"  on thread 1;
//   fork execution of another graph executor using "rendez" on thread 2;
//   ...
//   join threads 1 and 2;
//
// In the example above, execution in thread 1 and 2 communicates with
// each other by send/recv operations through the "rend".
//
// Tensors sent and recved through rendezvous managed by this
// RendezvousMgr must have keys generated by Rendezvous::CreateKey.

/**
 * @brief Rendezvous manager used by worker.
 * There are three related classes:
 * SalusRendezvousMgr creates WorkerRendezvous
 * WorkerRendezvous is passed to each ExecTask, and does the heavey lift
 * RendezvousWithHook is created internally inside each ExecTask, intercepting Send and Recv calls per device
 * and forwarding to WorkerRendezvous.
 */
class SalusRendezvousMgr : public tf::BaseRendezvousMgr
{
public:
    using BaseRendezvousMgr::BaseRendezvousMgr;

protected:
    tf::BaseRemoteRendezvous *Create(tf::int64 step_id, const tf::WorkerEnv *worker_env) override;

private:
    SALUS_DISALLOW_COPY_AND_ASSIGN(SalusRendezvousMgr);
};

class WorkerRendezvous : public tf::BaseRemoteRendezvous
{
public:
    using BaseRemoteRendezvous::BaseRemoteRendezvous;

    /**
     * @brief Keep a record of awaiting the tensor and then forward to base class.
     *
     * Inputs from run request are made available by GraphMgr using this method,
     * via a send from CPU device
     */
    Status Send(const ParsedKey &key, const Args &args, const tf::Tensor &val, const bool is_dead) override;

    /**
     * @brief Cleanup the record of awaiting tensors
     */
    void RecvAsync(const ParsedKey &key, const Args &args, DoneCallback done) override;

    /**
     * @brief Find a staged tensor with given key
     */
    bool FindTensor(const std::string &key, tf::Tensor &t);

protected:
    void RecvFromRemoteAsync(const ParsedKey &parsed, const Args &args, DoneCallback done) override;

    void SameWorkerRecvDone(const ParsedKey &parsed, const Args &in_args, const Args &out_args,
                            const tf::Tensor &in, tf::Tensor *out, tf::StatusCallback done) override;

private:
    ~WorkerRendezvous() override = default;

    std::mutex m_mu;
    std::unordered_map<std::string, tf::Tensor> m_tensors;

    SALUS_DISALLOW_COPY_AND_ASSIGN(WorkerRendezvous);
};

} // namespace salus::oplibtf

#endif // SALUS_OPLIB_TENSORFLOW_RENDEZVOUSMGR_H