import { Command, Declare, Options } from "seyfert";
import AppealSubCommand from "./appeal";
import ApproveSubCommand from "./approve";
import CheckSubCommand from "./check";
import DeclineSubCommand from "./decline";
import EnforceSubCommand from "./enforce";
import InfoSubCommand from "./info";
import ListSubCommand from "./list";
import LocalEnforceSubCommand from "./local-enforce";
import ReviewerAddSubCommand from "./reviewer-add";
import ReviewerListSubCommand from "./reviewer-list";
import ReviewerRemoveSubCommand from "./reviewer-remove";
import SubmitSubCommand from "./submit";

@Declare({
	name: "sanctions",
	description: "Manage the NationSeal shared sanction list",
	contexts: ["Guild"],
	integrationTypes: ["GuildInstall"],
	// No defaultMemberPermissions here so the command tree is visible to everyone.
	// Each subcommand gates itself in code and replies with a clear error when
	// the caller lacks the required permission or role.
	botPermissions: ["BanMembers"],
})
@Options([
	SubmitSubCommand,
	AppealSubCommand,
	ApproveSubCommand,
	DeclineSubCommand,
	CheckSubCommand,
	ListSubCommand,
	InfoSubCommand,
	EnforceSubCommand,
	LocalEnforceSubCommand,
	ReviewerAddSubCommand,
	ReviewerRemoveSubCommand,
	ReviewerListSubCommand,
])
export default class SanctionCommand extends Command {}
