# Storm Test

### Purpose

This is a data integrity stress test designed to verify the robustness of the communication protocol under a heavy load of varied data. It ensures that data is not corrupted during transmission, regardless of its length or content.

### How It Works

The test operates on an "echo" mechanism.

1.  **The Master** enters a nested loop. The outer loop iterates through slave addresses, and the inner loop iterates through a range of payload lengths (e.g., 1 to 255 bytes).
2.  For each combination, the master generates a random alphanumeric payload of the specified length.
3.  It sends this payload to the slave.
4.  **The Slave** is designed to be a simple "echo server." When it receives a payload, its only job is to send the exact same payload back to the master.
5.  **The Master** receives the echoed response and performs a strict validation, checking that both the length and the content of the response are a perfect match to what it originally sent.

A failure in this test indicates a potential issue in the protocol's byte-stuffing, CRC, or state-machine logic.

### Scripts

*   `storm_test_master.py`: The non-threaded master script. **It will terminate immediately** upon any failure (data mismatch or timeout).
*   `storm_test_slave.py`: A dynamic-address echo slave. It listens on an address, echoes all payloads it receives for a full length-test cycle, and then changes its address to follow the master.
*   `threaded_storm_test_master.py`: A threaded version of the master that uses a background I/O thread. Its test logic is identical to the non-threaded version and **it will also terminate immediately** upon any failure. Its primary purpose is to serve as a correct usage example for the `ThreadedMaster` class.

### How to Run

1.  **Configure Serial Ports** in the master and slave scripts you intend to use.
2.  **On the Slave machine**, run the slave script:
    ```bash
    python src/test_scripts/storm_test/storm_test_slave.py
    ```
3.  **On the Master machine**, run your chosen master script:
    ```bash
    # For the non-threaded version
    python src/test_scripts/storm_test/storm_test_master.py

    # OR for the threaded version
    python src/test_scripts/storm_test/threaded_storm_test_master.py
    ```