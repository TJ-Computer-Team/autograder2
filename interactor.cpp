#include <iostream>
#include <string>
using namespace std;

int main() {
    int secret;
    cin >> secret;
    
    string symbol;
    int value;
    cin >> symbol >> value;
    
    if (symbol == "?") {
        if (secret < value) {
            cout << ">" << endl;
        } else if (secret > value) {
            cout << "<" << endl;
        } else {
            cout << "=" << endl;
        }
    } else if (symbol == "!") {
        if (value == secret) {
            cout << "AC" << endl;
            return 0;
        } else {
            cout << "WA" << endl;
            return 1;
        }
    }
    
    return 0;
}

