/**
 * The few controls the panel needs, injectable per host: plain HTML here (Electron,
 * browser, tests); the Premiere panel passes Spectrum web components (UXP), so the
 * same views render in both (PL3 "two render targets").
 */
import type { ReactNode } from 'react';

export interface ButtonProps {
  children: ReactNode;
  onClick: () => void;
  variant?: 'cta' | 'primary' | 'secondary';
  disabled?: boolean;
}
export interface FieldProps<T> {
  label: string;
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
}
export interface SelectProps extends FieldProps<string> {
  options: { value: string; label: string }[];
}
export interface SliderProps extends FieldProps<number> {
  min: number;
  max: number;
  step: number;
  format?: (v: number) => string;
}
export interface CheckboxProps extends FieldProps<boolean> {}
export interface ProgressProps {
  value: number; // 0..1
  label: string;
}

export interface Primitives {
  Button(props: ButtonProps): ReactNode;
  TextField(props: FieldProps<string>): ReactNode;
  Select(props: SelectProps): ReactNode;
  Slider(props: SliderProps): ReactNode;
  Checkbox(props: CheckboxProps): ReactNode;
  Progress(props: ProgressProps): ReactNode;
}

const row = { display: 'flex', flexDirection: 'column' as const, gap: 2, margin: '4px 0' };
const labelStyle = { fontSize: 11, opacity: 0.75 };

export const htmlPrimitives: Primitives = {
  Button: ({ children, onClick, variant = 'secondary', disabled }) => (
    <button
      type="button"
      data-variant={variant}
      disabled={disabled}
      onClick={onClick}
      style={{
        padding: '4px 12px',
        borderRadius: 14,
        border: '1px solid currentColor',
        fontWeight: variant === 'secondary' ? 400 : 600,
        cursor: disabled ? 'default' : 'pointer',
      }}
    >
      {children}
    </button>
  ),
  TextField: ({ label, value, onChange, disabled }) => (
    <label style={row}>
      <span style={labelStyle}>{label}</span>
      <input
        aria-label={label}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  ),
  Select: ({ label, value, onChange, options, disabled }) => (
    <label style={row}>
      <span style={labelStyle}>{label}</span>
      <select
        aria-label={label}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  ),
  Slider: ({ label, value, onChange, min, max, step, format, disabled }) => (
    <label style={row}>
      <span style={labelStyle}>
        {label}: {format ? format(value) : value}
      </span>
      <input
        aria-label={label}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  ),
  Checkbox: ({ label, value, onChange, disabled }) => (
    <label style={{ display: 'flex', gap: 6, alignItems: 'center', margin: '4px 0' }}>
      <input
        aria-label={label}
        type="checkbox"
        checked={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>{label}</span>
    </label>
  ),
  Progress: ({ value, label }) => (
    <div style={row}>
      <span style={labelStyle}>{label}</span>
      <progress aria-label={label} max={1} value={value} style={{ width: '100%' }} />
    </div>
  ),
};
