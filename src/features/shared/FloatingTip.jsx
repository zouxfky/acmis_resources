export function FloatingTip({ tip }) {
  if (!tip) {
    return null;
  }

  return (
    <div className={`floating-tip${tip.status === "error" ? " is-error" : " is-success"}`}>
      {tip.message}
    </div>
  );
}
