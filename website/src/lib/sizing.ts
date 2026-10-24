import clsx from 'clsx';

export function colClasses(spans: number): string {
  return clsx('col', `col--${spans}`);
}
