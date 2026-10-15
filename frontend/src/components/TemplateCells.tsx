/** Face / Fingers / Photo cells for a user row: what the server holds for them (what readers have sent). */
export function TemplateCells({ user }: { user: any }) {
  const face = user.FaceCount || 0;
  const fingers = user.FingerCount || 0;
  return (
    <>
      <td>
        {face > 0
          ? <span className="badge badge-green" title="Face template received from a reader">✓</span>
          : user.HasFacePhoto
            ? <span className="badge badge-green" title="Face photo received from an AI-face reader: another AI reader builds its own face template from it">photo</span>
            : <span className="tpl-none">—</span>}
      </td>
      <td>{fingers > 0 ? <span className="badge badge-green" title={`${fingers} fingerprint(s) received from a reader`}>{fingers}</span> : <span className="tpl-none">—</span>}</td>
      <td>{user.HasPhoto ? <span className="badge badge-green" title="Photo received from a reader">✓</span> : <span className="tpl-none">—</span>}</td>
    </>
  );
}

export function templateTotals(users: any[]) {
  const withFace = users.filter((u) => (u.FaceCount || 0) > 0 || u.HasFacePhoto).length;
  const withFinger = users.filter((u) => (u.FingerCount || 0) > 0).length;
  const fingers = users.reduce((n, u) => n + (u.FingerCount || 0), 0);
  const withPhoto = users.filter((u) => u.HasPhoto).length;
  return { users: users.length, withFace, withFinger, fingers, withPhoto, any: withFace + withFinger > 0 };
}
