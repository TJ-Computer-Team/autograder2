#include "testlib.h"

using namespace std;

int main(int argc, char *argv[]) {
    // Initialize the testlib validator
    registerValidation(argc, argv);

    // Read the number of test cases t (1 <= t <= 1000)
    int t = inf.readInt(1, 1000, "t");
    inf.readEoln(); // Strictly expect a newline after t

    int sum_n = 0;
    for (int test = 1; test <= t; test++) {
        // Read n for the current test case (1 <= n <= 100000)
        int n = inf.readInt(1, 100000, "n");
        inf.readEoln();

        // Accumulate and strictly enforce the sum of N constraint
        sum_n += n;
        ensuref(sum_n <= 200000, "Sum of n over all test cases exceeds 200000 (failed at test %d)", test);

        // Read the array elements a_i
        for (int i = 0; i < n; i++) {
            // Read each element (1 <= a_i <= 100000)
            inf.readInt(1, 100000, "a_i");
            
            // Check for space between numbers, but strictly NO trailing space at the end of the line
            if (i + 1 < n) {
                inf.readSpace();
            }
        }
        inf.readEoln(); // Strictly expect a newline after the array
    }

    // Ensure there is absolutely no extra garbage or unparsed tokens at the end of the file
    inf.readEof();

    return 0;
}