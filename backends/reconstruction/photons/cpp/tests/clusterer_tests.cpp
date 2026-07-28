#include <string>

#include "clusterer.h"
#include "test_helpers.h"

int main() {
    TestContext test;

    // Placeholder test anchoring the ctest target for Stage 4.1. Clustering,
    // filtering, and correction tests are added in the following steps.
    test.expect(std::string(hermes_photon_clusterer::kVersion) == "0.1.0",
                "clusterer version is 0.1.0");

    return test.finish();
}
