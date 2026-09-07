const CARDS: { title: string; body: string }[] = [
  {
    title: 'Only app-owned calls/chats are analysed',
    body:
      'TrustGuard analyses calls and chats that flow through the TrustGuard demo apps. It never taps other apps, system call audio, or messaging platforms outside the demo environment.',
  },
  {
    title: 'No raw audio persisted',
    body:
      'Speech is transcribed on device or in the session pipeline and the raw audio is discarded immediately. Only text transcripts, scores and evidence metadata are retained for the session.',
  },
  {
    title: 'No keys in the APK',
    body:
      'LLM provider keys live server-side (data/providers.json behind the admin gateway). The Android APK ships with zero secrets — a leaked binary grants nothing.',
  },
  {
    title: 'Persistent analysis indicator on both phones',
    body:
      'While a session is being analysed, both devices show an unmissable on-screen indicator. Nobody is ever recorded or scored without seeing it.',
  },
  {
    title: 'Fictional bank names only',
    body:
      'All banks, brands and phone numbers used in demos (e.g. ApnaBank) are fictional. Any resemblance to real institutions is coincidental; scam samples use fabricated details only.',
  },
  {
    title: 'The score is computed by auditable deterministic code — the LLM proposes, code decides',
    body:
      'The LLM only proposes signal detections with confidences. A deterministic, inspectable rule engine converts those proposals into the final 0-100 score and band, so every point is explainable and reproducible from stored evidence.',
  },
];

export default function PrivacyTab() {
  return (
    <div className="tab-body">
      <h2 className="toolbar-title privacy-title">Privacy &amp; consent principles</h2>
      <div className="privacy-grid">
        {CARDS.map((c) => (
          <article key={c.title} className="panel privacy-card">
            <h3>{c.title}</h3>
            <p>{c.body}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
