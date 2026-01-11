# Git Deploy – Custom PaaS-Style Deployment Platform

Git Deploy is a self-hosted backend platform designed to automate Docker-based application deployments directly from GitHub repositories.  
The goal of this project is to understand how real-world deployment platforms (like Vercel or Railway) work internally.

---

## 🚀 Overview

This platform allows users to trigger deployments by providing GitHub repository details.  
The backend handles cloning the repository, building Docker images, running containers, and tracking deployment status with logs.

The project is focused on **backend workflows, deployment automation, and system reliability**, rather than UI.

---

## 🛠 Tech Stack

- **Backend:** FastAPI (Python)
- **Containerization:** Docker
- **Version Control:** Git, GitHub
- **Runtime Environment:** Linux
- **APIs:** RESTful APIs

---

## ✨ Key Features

- Trigger deployments directly from GitHub repositories
- Support for custom branch selection and build context
- Automated Docker image build and container execution
- Deployment lifecycle tracking:
  - Created
  - Prepared
  - Running
  - Error
- Build-time and runtime logging for debugging
- Framework-agnostic deployment (any app with a Dockerfile)

---

## 🔁 Deployment Flow

1. User sends a deployment request via REST API
2. Repository is cloned from GitHub
3. Docker image is built using the provided Dockerfile
4. Container is started with specified port mapping
5. Deployment status and logs are updated in real time

---

## 📌 Project Status

🚧 **Ongoing**

Planned improvements:
- Authentication for deployment APIs
- Nginx-based routing for multiple deployed apps
- Web UI for managing deployments
- Cloudflare Tunnel integration for secure public access

---

## 🎯 Learning Objectives

- Understand real-world deployment workflows
- Work with Docker programmatically
- Handle failures and container crashes
- Design backend systems with clear state management

---

## 📫 Author

**Abhishek Chaurasiya**  
- GitHub: https://github.com/abhishekabck  
- LinkedIn: https://www.linkedin.com/in/abhishek-chaurasiya-501547224/
