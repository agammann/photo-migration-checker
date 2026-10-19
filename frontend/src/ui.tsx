import type { ReactNode } from 'react';

export function Icon({ name, size = 20 }: { name: 'arrow' | 'search' | 'check' | 'warning' | 'cross' | 'folder' | 'download'; size?: number }) {
  const paths = {
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
    check: <><circle cx="12" cy="12" r="10" fill="currentColor" stroke="none" /><path d="m7.5 12 3 3 6-6" stroke="white" /></>,
    cross: <><circle cx="12" cy="12" r="10" fill="currentColor" stroke="none" /><path d="m8.5 8.5 7 7m0-7-7 7" stroke="white" /></>,
    warning: <><path d="M10.25 3.5a2 2 0 0 1 3.5 0l8 14a2 2 0 0 1-1.75 3h-16a2 2 0 0 1-1.75-3z" fill="currentColor" stroke="none" /><path d="M12 8v5.5" stroke="white" /><circle cx="12" cy="17" r="1" fill="white" stroke="none" /></>,
    folder: <><path d="M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z" /></>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export function Banner({ title, children, tone = 'warning' }: { title: string; children: ReactNode; tone?: 'warning' | 'info' | 'error' }) {
  return <div className={`banner banner-${tone}`}><Icon name={tone === 'error' ? 'cross' : 'warning'} size={29} /><div><strong>{title}</strong><div>{children}</div></div></div>;
}

export function PageHeading({ title, subtitle, children }: { title: string; subtitle: string; children?: ReactNode }) {
  const sourceTitle = title === 'Start with your Takeout.';
  const resultsTitle = title === 'Your migration, checked.';
  return <div className={`page-heading ${sourceTitle ? 'source-heading' : ''} ${resultsTitle ? 'results-heading' : ''}`}><div><h1 aria-label={title} tabIndex={-1}>{sourceTitle ? <><span>Start with</span>{' '}<span>your</span>{' '}<span className="accent-text">Takeout.</span></> : resultsTitle ? <>Your migration, <span className="accent-text">checked.</span></> : title}</h1><p>{subtitle}</p></div>{children ? <div className="heading-actions">{children}</div> : null}</div>;
}

export function bytes(value: number | undefined) {
  if (!value) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const power = Math.min(Math.floor(Math.log(value) / Math.log(1024)), 4);
  return `${new Intl.NumberFormat('en', { maximumFractionDigits: power > 0 ? 1 : 0 }).format(value / 1024 ** power)} ${units[power]}`;
}

export function humanize(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/, (letter) => letter.toUpperCase());
}
