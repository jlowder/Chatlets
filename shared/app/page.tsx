import ChatPage from '@/components/ChatPage';

const backendName = process.env.CHATLET_BACKEND || 'vercel-ai';

export default function Page() {
  return <ChatPage frameworkName={backendName} />;
}
