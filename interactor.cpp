#include <iostream>
#include <string>
#include <sstream>
using namespace std;

int main() {
    string line;
    
    // Read secret number
    if (!getline(cin, line)) return 1;
    int secret = stoi(line);
    
    // Read command
    if (!getline(cin, line)) return 1;
    string command = line;
    
    // Handle MAX_QUERIES
    if (command == "MAX_QUERIES") {
        cout << 10 << endl;
        return 0;
    }
    
    // Handle query (?)
    if (command[0] == '?') {
        int query = stoi(command.substr(1));
        if (query == secret) {
            cout << "=" << endl;
        } else if (secret < query) {
            cout << "<" << endl;
        } else {
            cout << ">" << endl;
        }
        return 0;
    }
    
    // Handle answer (!)
    if (command[0] == '!') {
        int answer = stoi(command.substr(1));
        if (answer == secret) {
            cout << "AC" << endl;
        } else {
            cout << "WA" << endl;
        }
        return 0;
    }
    
    return 1;
}
