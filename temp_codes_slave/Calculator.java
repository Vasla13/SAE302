public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
    public int subtract(int a, int b) {
        return a - b;
    }
    public int multiply(int a, int b) {
        return a * b;
    }
    public int divide(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException("Cannot divide by zero");
        }
        return a / b;
    }

    // Méthode main pour exécuter et tester la classe
    public static void main(String[] args) {
        Calculator calc = new Calculator();
        System.out.println("3 + 2 = " + calc.add(3, 2));
        System.out.println("5 - 2 = " + calc.subtract(5, 2));
        System.out.println("4 * 6 = " + calc.multiply(4, 6));
        System.out.println("10 / 2 = " + calc.divide(10, 2));
    }
}
