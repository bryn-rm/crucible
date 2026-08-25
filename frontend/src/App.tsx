import { useState } from 'react';
import { MatchView } from './match/MatchView';
import { ReplayView } from './replay/ReplayView';
import { LeaderboardView } from './leaderboard/LeaderboardView';
import { TournamentView } from './tournament/TournamentView';

type Tab = 'match' | 'tournament' | 'replay' | 'leaderboard';

const TABS: { id: Tab; label: string }[] = [
  { id: 'match', label: 'Match' },
  { id: 'tournament', label: 'Tournament' },
  { id: 'replay', label: 'Replay' },
  { id: 'leaderboard', label: 'Leaderboard' },
];

function App() {
  const [tab, setTab] = useState<Tab>('match');
  const [token, setToken] = useState(() => sessionStorage.getItem('arena_api_token') ?? '');
  const [tokenInput, setTokenInput] = useState('');

  if (!token) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md items-center px-6 text-neutral-100">
        <form
          className="setup-card w-full"
          onSubmit={(event) => {
            event.preventDefault();
            const value = tokenInput.trim();
            if (!value) return;
            sessionStorage.setItem('arena_api_token', value);
            setToken(value);
          }}
        >
          <span className="eyebrow">Protected arena</span>
          <h1>Enter the arena access token.</h1>
          <label>
            Access token
            <input
              type="password"
              autoComplete="current-password"
              value={tokenInput}
              onChange={(event) => setTokenInput(event.target.value)}
            />
          </label>
          <button className="start-button" type="submit" disabled={!tokenInput.trim()}>
            Enter arena
          </button>
        </form>
      </main>
    );
  }

  return (
    <div className="mx-auto min-h-screen max-w-6xl px-6 py-8 text-neutral-100">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-medium tracking-tight">CRUCIBLE <span className="text-xs text-emerald-300">/ ARENA</span></h1>
        <nav className="flex gap-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-md px-3 py-1.5 text-sm ${
                tab === t.id
                  ? 'bg-neutral-100 text-neutral-950'
                  : 'text-neutral-400 hover:text-neutral-100'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <div hidden={tab !== 'match'}><MatchView /></div>
      {tab === 'tournament' && <TournamentView />}
      {tab === 'replay' && <ReplayView />}
      {tab === 'leaderboard' && <LeaderboardView />}
    </div>
  );
}

export default App;
