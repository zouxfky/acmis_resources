import { WorkspaceContainerGrid } from "./WorkspaceContainerGrid";
import { WorkspaceOverview } from "./WorkspaceOverview";


export function WorkspacePage({
  session,
  sshKeys,
  joinedContainers,
  workspaceContainers,
  workspaceMessage,
  workspaceLoading,
  onOpenJoinDialog,
  onOpenLeaveDialog,
  onCopySshCommand
}) {
  return (
    <>
      <WorkspaceOverview
        joinedContainers={joinedContainers}
        session={session}
        sshKeys={sshKeys}
        workspaceContainers={workspaceContainers}
        onCopySshCommand={onCopySshCommand}
      />

      <section className="dashboard-content no-sidebar">
        {workspaceMessage ? <div className="notice is-error">{workspaceMessage}</div> : null}

        <WorkspaceContainerGrid
          sshKeys={sshKeys}
          workspaceContainers={workspaceContainers}
          workspaceLoading={workspaceLoading}
          onOpenJoinDialog={onOpenJoinDialog}
          onOpenLeaveDialog={onOpenLeaveDialog}
        />
      </section>
    </>
  );
}
