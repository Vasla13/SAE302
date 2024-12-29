#include <iostream>
using namespace std;

int main() {
    int sum = 0;
    for(int i = 1; i <= 5; i++) {
        sum += i;
    }
    cout << "La somme des entiers de 1 a 5 est : " << sum << endl;
    return 0;
}
