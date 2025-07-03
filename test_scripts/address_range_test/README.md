# Address Range Test

### Purpose

This test verifies basic connectivity and responsiveness across a wide range of slave addresses. It ensures that the master can successfully communicate with a slave regardless of the address it is assigned.

### How It Works

The test operates on a simple "ping-pong" mechanism.

1.  **The Master** sends a `ping` message to the first address in the test range (e.g., address 1).
2.  **The Slave**, which is dynamically changing its own address, listens on address 1. When it receives the `ping`, it responds with a `pong`.
3.  After sending the `pong`, the slave script automatically changes its listening address to the next one in the sequence (e.g., address 2).
4.  After the master receives a successful `pong` (or times out), it also moves on to test the next address.
5.  This process repeats for the entire configured address range.

This unique design allows a single physical slave device to simulate an entire bus full of slaves.

### Scripts

*   `address_range_test_master.py`: The non-threaded master script. It sends pings and waits for pongs in a single-threaded loop.
*   `address_range_test_slave.py`: The dynamic-address slave script. It responds to pings and then increments its own listening address.
*   `threaded_address_range_test_master.py`: A threaded version of the master that demonstrates the use of the `ThreadedMaster` class. It runs the I/O loop in a background thread and makes blocking requests from the main thread.

### How to Run

1.  **Configure Serial Ports** in the master and slave scripts you intend to use.
2.  **On the Slave machine**, run the slave script:
    ```bash
    python src/test_scripts/address_range_test/address_range_test_slave.py
    ```
3.  **On the Master machine**, run your chosen master script:
    ```bash
    # For the non-threaded version
    python src/test_scripts/address_range_test/address_range_test_master.py

    # OR for the threaded version
    python src/test_scripts/address_range_test/threaded_address_range_test_master.py
    ```