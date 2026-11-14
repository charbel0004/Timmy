export function workspaceLocation(hash: string) {
  const review = /^#imports\/validation\/([1-9][0-9]*)$/.exec(hash);
  return review
    ? { page: "imports", validationId: review[1] }
    : { page: hash.slice(1), validationId: undefined };
}
