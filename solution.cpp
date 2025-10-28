#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    
    int T;
    cin >> T;
    
    while (T--) {
        int lo = 1, hi = 1000;
        int answer = -1;
        
        for (int q = 0; q < 10; q++) {
            if (lo > hi) break;
            
            int mid = (lo + hi) / 2;
            cout << "? " << mid << endl;
            
            string resp;
            cin >> resp;
            
            if (resp == "=") {
                answer = mid;
                break;
            } else if (resp == "<") {
                // secret < mid, search lower
                hi = mid - 1;
            } else {  // resp == ">"
                // secret > mid, search higher
                lo = mid + 1;
            }
        }
        
        // If we found the answer, output it
        // Otherwise output our best guess (should be lo when lo==hi)
        if (answer != -1) {
            cout << "! " << answer << endl;
        } else {
            // After binary search, lo should equal hi (or lo > hi)
            // The secret should be at lo
            cout << "! " << lo << endl;
        }
    }
    
    return 0;
}
