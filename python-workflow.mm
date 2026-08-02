graph LR
    Client["Client<br/>Browser"] -->|fetch /api/chat| Proxy["Shared Frontend<br/>Next.js :3000"]
    Proxy -->|rewrite based on<br/>CHATLET_BACKEND| PythonProxy["Python Backend<br/>Next.js proxy :5009"]
    PythonProxy -->|forward to| Agent["Flask agent :5008"]
