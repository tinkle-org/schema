import React from 'react';
import clsx from 'clsx';
import { colClasses } from '@site/src/lib/sizing';

type ColProps = React.PropsWithChildren<{
  oneHalf?: boolean;
  oneThird?: boolean;
  className?: string;
}>;

export function Col({ oneHalf, oneThird, className, children }: ColProps) {
  return (
    <div className={clsx(oneHalf && colClasses(6), oneThird && colClasses(4), className)}>
      {children}
    </div>
  );
}

type GridProps = React.PropsWithChildren<{ className?: string }>;

export default function Grid({ className, children }: GridProps) {
  return <div className={clsx('siteGridWrap', 'row', className)}>{children}</div>;
}
