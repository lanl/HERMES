#ifndef HERMES_EVENT_RECONSTRUCTOR_TEST_HELPERS_H
#define HERMES_EVENT_RECONSTRUCTOR_TEST_HELPERS_H

#include <iostream>
#include <string>

class TestContext {
  public:
    void expect(const bool condition, const std::string& message) {
        if (!condition) {
            std::cerr << "FAIL: " << message << '\n';
            ++failures_;
        }
    }

    template <typename Actual, typename Expected>
    void expectEqual(const Actual& actual,
                     const Expected& expected,
                     const std::string& message) {
        if (actual != expected) {
            std::cerr << "FAIL: " << message << " (actual=" << actual
                      << ", expected=" << expected << ")\n";
            ++failures_;
        }
    }

    int finish() const {
        if (failures_ == 0) {
            return 0;
        }
        std::cerr << failures_ << " assertion(s) failed\n";
        return 1;
    }

  private:
    int failures_ = 0;
};

#endif
