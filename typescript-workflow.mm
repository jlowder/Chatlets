graph LR
    Client["Client<br/>Browser"] -->|fetch /api/chat| Proxy["Shared Frontend<br/>Next.js :3000"]
    Proxy -->|rewrite based on<br/>CHATLET_BACKEND| TSBackend["TypeScript Backend<br/>e.g. vercel-ai :4000"]
