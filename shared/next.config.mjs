/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const backend = process.env.CHATLET_BACKEND || 'vercel-ai';
    const backends = {
      'vercel-ai': { url: 'http://localhost:4000', path: '/api/chat' },
      'agno': { url: 'http://localhost:3001', path: '/api/chat' },
      'crewai': { url: 'http://localhost:5000', path: '/chat' },
    };
    const { url, path: destPath } = backends[backend];
    if (!url) return [];
    return [
      {
        source: '/api/chat',
        destination: `${url}${destPath}`,
      },
    ];
  },
};

export default nextConfig;
