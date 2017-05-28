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

#ifndef TFOPLIBRARY_H
#define TFOPLIBRARY_H

#include "ioplibrary.h"

#include "executor.pb.h"

#include <tensorflow/core/framework/op_segment.h>

#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>

namespace tensorflow {
class OpKernel;
class OpKernelContext;
class OpSegment;
class OptimizerOptions;
class NodeDef;
class FunctionDefLibrary;
class ConfigProto;
}

class TFOpLibrary;
class TFDevice;
class TFSession;

class TFTask : public ITask
{
public:
    ~TFTask() override = default;

    TFTask(TFOpLibrary *library, std::unique_ptr<tensorflow::OpKernel> &&kernel,
           std::unique_ptr<tensorflow::OpKernelContext> &&context);

    executor::Status run() override;
    executor::OpContextDef contextDef() override;

private:
    std::unique_ptr<tensorflow::OpKernel> m_opkernel;
    std::unique_ptr<tensorflow::OpKernelContext> m_context;
    TFOpLibrary *m_library;
};

/**
 * @todo write docs
 */
class TFOpLibrary : public IOpLibrary
{
public:
    ~TFOpLibrary() override = default;

    bool accepts(const executor::OpKernelDef &operation) override;
    std::unique_ptr<ITask> createTask(const executor::OpKernelDef &opdef,
                                      const executor::OpContextDef &ctxdef) override;

    std::unique_ptr<tensorflow::OpKernel> kernelFromDef(const executor::OpKernelDef &opdef);
    std::unique_ptr<tensorflow::OpKernelContext> contextFromDef(const executor::OpContextDef &ctxdef);
    executor::OpContextDef contextToDef(const tensorflow::OpKernelContext *context);

private:
    TFSession *getOrCreateSession(const std::string &sess_id, int graph_def_version,
                                  const tensorflow::ConfigProto &cfgProto,
                                  const tensorflow::FunctionDefLibrary &fDefLib);

    std::mutex m_mu; // protects m_sessions
    std::unordered_map<std::string, std::unique_ptr<TFSession>> m_sessions;
};

class TFSession
{
public:
    TFSession(TFOpLibrary *opLibrary, const tensorflow::FunctionDefLibrary &fDefLib,
              int graphDefVersion, const tensorflow::OptimizerOptions &optimizerOpts);

    ~TFSession();

    std::unique_ptr<tensorflow::OpKernel> createKernel(const tensorflow::NodeDef &nodedef);

private:
    TFOpLibrary *m_oplibrary;

    tensorflow::OpSegment m_opseg;
    tensorflow::FunctionLibraryDefinition m_flibDef;
    std::unique_ptr<tensorflow::FunctionLibraryRuntime> m_fruntime;
    std::unique_ptr<TFDevice> m_device;
};
#endif // TFOPLIBRARY_H
