import type { CommandContext } from "seyfert";
import { config } from "../config";
import { reviewers } from "./db";

/** Owners manage the reviewer roster. They are always treated as reviewers too. */
export function isOwner(userId: string): boolean {
	return config.ownerIds.includes(userId);
}

export async function isReviewer(userId: string): Promise<boolean> {
	if (isOwner(userId)) return true;
	return reviewers.isReviewer(userId);
}

export async function hasAdministrator(ctx: CommandContext): Promise<boolean> {
	const member = ctx.member;
	if (!member) return false;

	try {
		const permissions = await member.fetchPermissions();
		return permissions.has(["Administrator"]);
	} catch {
		return false;
	}
}

export async function requireReviewer(ctx: CommandContext): Promise<boolean> {
	if (await isReviewer(ctx.author.id)) return true;

	await ctx.editOrReply({
		content: "Only trusted NationSeal reviewers can use this command.",
	});
	return false;
}

export async function requireOwner(ctx: CommandContext): Promise<boolean> {
	if (isOwner(ctx.author.id)) return true;

	await ctx.editOrReply({
		content: "Only NationSeal owners can use this command.",
	});
	return false;
}
