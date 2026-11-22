#pragma once

// A few worker threads for work the gpu thread would otherwise stall on
// (compiling shaders, creating pipelines). A job runs once, on a worker or
// on whichever thread asks for it finished first: finish() takes a job no
// worker has started and runs it there, else waits for the worker that has
// it. So a job may finish other jobs (a pipeline its shaders) without a
// deadlock: whoever waits, waits on a job that is running.

#include <atomic>
#include <condition_variable>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>

namespace cafe::gpu::vk {

class JobPool {
public:
    struct Job {
        std::function<void()> run;
        std::atomic<uint8_t> state{0}; // 0 queued, 1 running, 2 done
    };
    using Ref = std::shared_ptr<Job>;

    JobPool() = default;
    JobPool(const JobPool&) = delete;
    JobPool& operator=(const JobPool&) = delete;
    ~JobPool() { stop(); }

    void start(unsigned threads) {
        for (unsigned i = 0; i < threads; ++i) workers_.emplace_back([this] { work(); });
    }

    // Jobs still queued are dropped (finish() can still run one); the
    // workers finish what they have and are joined.
    void stop() {
        {
            std::lock_guard lock(mutex_);
            stopping_ = true;
            queue_.clear();
        }
        wake_.notify_all();
        for (std::thread& t : workers_) t.join();
        workers_.clear();
    }

    Ref submit(std::function<void()> run) {
        Ref job = std::make_shared<Job>();
        job->run = std::move(run);
        {
            std::lock_guard lock(mutex_);
            queue_.push_back(job);
        }
        wake_.notify_one();
        return job;
    }

    static bool done(const Ref& job) { return job->state.load(std::memory_order_acquire) == 2; }

    // Returns with the job done. True: it ran here.
    bool finish(const Ref& job) {
        if (take(*job)) return true;
        std::unique_lock lock(mutex_);
        finished_.wait(lock, [&] { return done(job); });
        return false;
    }

    size_t queued() {
        std::lock_guard lock(mutex_);
        return queue_.size();
    }

private:
    bool take(Job& job) {
        uint8_t queued = 0;
        if (!job.state.compare_exchange_strong(queued, 1)) return false;
        job.run();
        job.run = nullptr;
        {
            std::lock_guard lock(mutex_);
            job.state.store(2, std::memory_order_release);
        }
        finished_.notify_all();
        return true;
    }

    void work() {
        for (;;) {
            Ref job;
            {
                std::unique_lock lock(mutex_);
                wake_.wait(lock, [&] { return stopping_ || !queue_.empty(); });
                if (stopping_) return;
                job = std::move(queue_.front());
                queue_.pop_front();
            }
            take(*job);
        }
    }

    std::mutex mutex_;
    std::condition_variable wake_, finished_;
    std::deque<Ref> queue_;
    std::vector<std::thread> workers_;
    bool stopping_ = false;
};

} // namespace cafe::gpu::vk
