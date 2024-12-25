#include <stdio.h>

int main() {
    int sum = 0;
    for(int i = 1; i <= 5; i++) {
        sum += i;
    }
    printf("La somme des entiers de 1 a 5 est : %d\n", sum);
    return 0;
}
