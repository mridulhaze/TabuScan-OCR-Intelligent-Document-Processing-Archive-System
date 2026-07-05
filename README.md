TabuScan OCR – Intelligent Document Processing & Archive System
Technologies Used: Python, Flask, OpenCV, EasyOCR (PyTorch), pyodbc, MS SQL Server, JavaScript (ES6+), HTML5, CSS3, Tkinter, PyInstaller.
Project Description:
Engineered a secure, full-stack enterprise document processing and archival platform that automates the digitization, indexing, and verification of historical tabulation sheets. The system bridges local filesystem operations and MS SQL Server databases through an optimized OCR pipeline, complete with a standalone desktop management console.
Key Contributions & Achievements (for CV Bullet Points):

High-Speed OCR Pipeline: Developed an intelligent OCR extraction pipeline using OpenCV and EasyOCR. Optimized scanning speeds by 5x (reducing processing time from 52s to ~10s per sheet) by implementing region-of-interest (ROI) coordinate cropping and custom character-noise filters.
Database & Blob Archival: Integrated Flask with MS SQL Server using pyodbc to store structured student indexes alongside scanned tabulation sheets stored directly as high-resolution binary blobs (VARBINARY(MAX)).
Desktop Controller Utility: Developed a standalone Win32 desktop console GUI using Tkinter and packaged it with PyInstaller. Built-in features include asynchronous background service execution, a real-time terminal logger, and an automated dependency installer utilizing subprocess pip wrappers.
Three-Tier Role-Based Security (RBAC): Built a secure multi-tier authentication system mapping strict privileges for different operators: Admin (AP) with full user CRUD dashboards; Viewer (PRO) with read-only search access; and Operator (USER) restricted to upload-and-verify pipelines.
Interactive Image Canvas: Created an advanced browser-based image workspace featuring hardware-accelerated drag-to-pan, scroll-wheel zoom, and real-time GPU-rendered CSS filters (Contrast Boost / Color Invert) to aid operators in reading low-contrast negative microfilms.
Real-time Data Linting: Implemented interactive client-side data validation that flags duplicate records and OCR noise in real-time, drastically reducing human error during database insertions. Included automated CSV reporting.
