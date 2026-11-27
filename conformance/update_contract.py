"""Expected public update contract. Do not derive these inventories from HEAD."""

BASELINE = "33b065883db8dc1f1b34cfe3ca0d9d9d0095e10f"
PRE_CALL_BASELINE = "8d769f9749e6c221a231df27746d2b1886fba29d"
UPDATE_FILE = "tinkle/v1/update.proto"
APPLICATION_UPDATES_FILE = "tinkle/v1/application_updates.proto"

# Original owner -> new owner -> declarations (nested declarations move with their parent).
MOVES = {
    "messages": {
        "message_updates": "MessageChanged ReactionEffect SendStatusChanged",
        "chat_updates": "TypingChanged ChatPhotoUpdateChanged ChatPhotoRepresentationChanged",
        "message_types": "Chat ChatPhoto ChatType Document GeoPoint Media Message MessageContact "
                         "MessageReactions MessageReplies MessageReplyHeader MessageScheduledState "
                         "PeerReaction Photo Poll PollAnswer PollAnswerResult PollResults Reaction ReactionCount "
                         "TypingAction TargetChangeKind RoomQueryTarget RoomOnlineCountSample DraftMessage",
    },
    "account": {
        "account_types": "NotificationSetting",
        "account_updates": "SessionChanged ProfilePhotoUpdateChanged ProfilePhotoRepresentationChanged",
    },
    "bots": {"bot_types": "BotCommandScope BotCommandScopeDefault BotCommandScopeAllPrivateChats "
                         "BotCommandScopeAllGroupChats BotCommandScopeAllChatAdministrators "
                         "BotCommandScopeChat BotCommandScopeChatParticipant"},
    "stickers": {"sticker_updates": "AssetChangeChanged StickerAssetRepresentationChanged",
                 "sticker_types": "PackKind"},
    "updates": {"application_updates": "ConnectivityChanged"},
    "channels": {"chat_updates": "ChannelPhotoUpdateChanged"},
}

MOVED_TO = {(f"tinkle/v1/{old}.proto", name): f"tinkle/v1/{new}.proto"
            for old, leaves in MOVES.items() for new, names in leaves.items() for name in names.split()}


def current_filename(filename, qualified_name):
    parent = qualified_name.removeprefix("tinkle.v1.").split(".", 1)[0]
    return MOVED_TO.get((filename, parent), filename)


# Existing mutations receive one direct field after their last 33b0658 tag.
_COMMANDS = """
SendMessage SetDraft SetDialogPin MoveDialogToSpace
CancelScheduledMessages ClosePoll MarkHistoryRead DeleteHistory DeleteMessages CreateChat
EditChatTitle EditChatPhoto UpdateChatDescription AddChatParticipant RemoveChatParticipant
EditChatAdmin EditChatRestrictedScopes SetHistoryTTL SetMessagePin UnpinAllMessages SendMedia
SendAlbum CancelSend CancelChatPhotoUpdate EditMessage StartBot SendReaction ReadMentions
ReadReactions SendVote ReadThread
CreateChannel DeleteChannel EditAdmin EditBanned DeleteParticipantHistory JoinChannel LeaveChannel
InviteToChannel ToggleParticipantsHidden TogglePreHistoryHidden ChannelsServiceUpdateUsername
ChannelsServiceToggleUsername EditTitle EditPhoto CancelPhotoUpdate ToggleSlowMode ToggleJoinRequest
HideJoinRequest HideAllJoinRequests ReadChannelHistory DeleteChannelMessages DeleteChannelHistory
UpdateNotificationSetting ResetNotificationSettings SetPrivacy UpdateProfile UpdateUsername
ChangePhoneNumber SetContentSetting RevokeSession RevokeSessions ConfirmSession SetProfilePhoto
CancelProfilePhotoUpdate SelectProfilePhoto DeleteProfilePhoto
ImportContacts AddContact DeleteContacts DeleteByPhones ResetSaved Block Unblock
SetCommands ResetCommands SetMenuButton SetGroupDefaultAdminScopes SetBroadcastDefaultAdminScopes
SetInfo ToggleUsername ReorderUsernames AllowSendMessage EditUserInfo
InstallPack UninstallPack ReorderPacks SaveRecentSticker ClearRecentStickers ToggleFavoriteSticker
CreateStickerAsset UpdateStickerAsset CancelAssetChange DeleteStickerAsset CreatePack UpdatePack
DeletePack AddPackAsset RemovePackAsset ReorderPackAssets PublishPack UnpublishPack
"""
UPDATE_RESPONSES = {method + "Response" for method in _COMMANDS.split()}

CALL_METHODS = """
GetCallConfiguration StartCall AcknowledgeIncomingCall AcceptCall DeclineCall CancelCall EndCall
GetCall ListActiveCalls GetCallConnection SendCallSignal ListCallSignals AcknowledgeCallSignals
RestartCallConnection ReportCallConnectionState SetCallMediaState
""".split()
GROUP_CALL_METHODS = """
CreateGroupCall GetGroupCall ListGroupCalls JoinGroupCall LeaveGroupCall EndGroupCall
StartScheduledGroupCall CancelScheduledGroupCall SetGroupCallStartReminder GetGroupCallParticipants
ListGroupCallParticipants InviteGroupCallParticipants DeclineGroupCallInvitation RemoveGroupCallParticipant
SetGroupCallTitle UpdateGroupCallSettings SetGroupCallParticipantRole SetGroupCallParticipantRestrictions
SetGroupCallHandRaised ListGroupCallInvitations GetGroupCallConnection NegotiateGroupCallConnection
RestartGroupCallConnection SetGroupCallMediaState StartCallPresentation StopCallPresentation
ListCallPresentations ListCallHistory DeleteCallHistory SetCallRating SubmitCallDiagnostics
""".split()
CALL_METHODS += GROUP_CALL_METHODS
PRIVATE_COMMANDS = "NegotiateGroupCallConnection SetCallRating SubmitCallDiagnostics"
UPDATE_RESPONSES.update(method + "Response" for method in GROUP_CALL_METHODS
                        if not method.startswith(("Get", "List")) and method not in PRIVATE_COMMANDS.split())
UPDATE_RESPONSES.update(method + "Response" for method in (
    "StartCall", "AcceptCall", "DeclineCall", "CancelCall", "EndCall",
    "RestartCallConnection", "ReportCallConnectionState", "SetCallMediaState"))

SOCIAL_METHODS = """
PublishDaily GetDaily EditDaily DeleteDaily ListDailies ListDailyFeed ListDailyArchive
MarkDailySeen BatchGetDailyAvailability PublishPost GetPost EditPost DeletePost ListPosts
ListPostFeed SetPostLike SaveDailyAsPost
""".split()
SOCIAL_UPDATE_RESPONSES = {method + "Response" for method in SOCIAL_METHODS
                           if not method.startswith(("Get", "List", "BatchGet"))}
UPDATE_RESPONSES.update(SOCIAL_UPDATE_RESPONSES)

NEW_SERVICE_METHODS = {
    "AnalyticsService": "GetAnalyticsAccess GetChannelStats GetGroupStats GetMessageStats GetDailyStats "
                        "GetPostStats GetPollStats GetAnalyticsSeries".split(),
    "PaymentsService": "CreateInvoice ClaimStoreCheckout GetInvoice GetPaymentForm ValidatePaymentDetails SubmitPayment GetPayment "
                       "ListPayments GetPaymentReceipt CreateRefund GetRefund VerifyStorePurchase GetMyEntitlements".split(),
    "BoostsService": "GetBoostConfiguration GetMyBoosts ApplyBoosts GetBoostStatus ListBoosts GetUserBoosts".split(),
}
UPDATE_RESPONSES.update(method + "Response" for method in (
    "CreateInvoice", "ClaimStoreCheckout", "SubmitPayment", "CreateRefund", "VerifyStorePurchase", "ApplyBoosts"))

# These commands exist but their public replies do not carry updates. In particular,
# BotApiService.SendMessage is a different handler from MessagesService.SendMessage.
COMMANDS_WITHOUT_UPDATES = {
    "AccountService": "RegisterPush UnregisterPush DeleteAccount SendChangePhoneCode Logout",
    "AuthService": "SendCode SignIn ResumeEnrollment ActivateEnrollment RotateEnrollment",
    "BotApiService": "SendMessage SendPhoto SendDocument SendVideo SendAudio SendVoice SendSticker "
                     "SendLocation SendContact ForwardMessage CopyMessage EditMessageText EditMessageCaption "
                     "EditMessageMedia EditMessageReplyMarkup DeleteMessage BanChatParticipant UnbanChatParticipant "
                     "RestrictChatParticipant PromoteChatParticipant LeaveChat SetWebhook DeleteWebhook AnswerCallbackQuery",
    "BotsService": "SendCustomRequest AnswerWebhookQuery",
    "CallsService": "AcknowledgeIncomingCall SendCallSignal AcknowledgeCallSignals " + PRIVATE_COMMANDS,
    "ConnectionService": "InitConnect KeepAlive",
    "FilesService": "BeginUpload UploadPart CompleteUpload AbortUpload DownloadPart",
    "HelpService": "SaveAppLog AcceptTermsOfService",
    "MessagesService": "SetTyping",
}

# Wire order, starting at tag 1.
CASE_LEAVES = [
    ("message", "MessageAdded MessageEdited MessagesRemoved HistoryChanged MessageAccepted MessagePinsChanged "
                "MessageReactionsChanged PollChanged ThreadChanged ScheduledMessagesChanged RecentReactionsChanged "
                "MessageChanged SendStatusChanged"),
    ("dialog", "DialogChanged DialogRemoved ReadStateChanged DraftChanged UnreadMentionsChanged UnreadReactionsChanged"),
    ("chat", "ChatAdded ChatChanged ChatRemoved ChatMembersChanged ChatMemberPermissionsChanged ChatSettingsChanged "
             "JoinRequestsChanged ConversationAccessChanged"),
    ("account", "UserChanged"),
    ("contact", "ContactsChanged PeerBlockChanged"),
    ("account", "PrivacyChanged NotificationSettingsChanged ContentSettingsChanged ProfilePhotosChanged SessionChanged"),
    ("sticker", "InstalledPacksChanged StickerPackChanged StickerAssetChanged RecentStickersChanged FavoriteStickersChanged"),
    ("chat", "ChatPhotoUpdateChanged ChannelPhotoUpdateChanged"),
    ("account", "ProfilePhotoUpdateChanged"),
    ("sticker", "AssetChangeChanged"),
    ("chat", "ChatPhotoRepresentationChanged"),
    ("account", "ProfilePhotoRepresentationChanged"),
    ("sticker", "StickerAssetRepresentationChanged"),
    ("bot", "BotCommandsChanged BotMenuChanged BotChanged BotPermissionsChanged"),
    ("chat", "TypingChanged"),
    ("application", "ConnectivityChanged"),
    ("chat", "RoomOnlineCountChanged"),
    ("application", "ConfigurationChanged WorkforceUserInfoChanged ReconciliationRequired"),
    ("call", "CallChanged CallSignalsAvailable CallConnectionRefreshRequired"),
    ("call", "GroupCallChanged GroupCallParticipantsChanged GroupCallInvitationChanged GroupCallStartReminderChanged "
             "CallPresentationChanged CallHistoryChanged GroupCallAccessChanged"),
    ("social", "DailyChanged DailyRemoved DailyAvailabilityChanged DailySeenChanged PostChanged PostRemoved PostLikesChanged"),
    ("payment", "PaymentChanged RefundChanged MyEntitlementsChanged"),
    ("boost", "MyBoostsChanged BoostStatusChanged"),
]
CASE_FILES = {name: f"tinkle/v1/{domain}_updates.proto"
              for domain, names in CASE_LEAVES for name in names.split()}
