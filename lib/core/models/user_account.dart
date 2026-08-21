class UserAccount {
  const UserAccount({
    required this.id,
    required this.username,
    required this.displayName,
    required this.role,
    required this.status,
    required this.createdAt,
    this.email = '',
    this.lastLoginAt,
  });

  final String id;
  final String username;
  final String displayName;
  final String role;
  final String status;
  final String createdAt;
  final String email;
  final String? lastLoginAt;

  bool get isAdministrator => role == 'admin';
  String get label => displayName.trim().isEmpty ? username : displayName;

  factory UserAccount.fromJson(Map<String, dynamic> json) => UserAccount(
        id: json['id'] as String? ?? '',
        username: json['username'] as String? ?? '',
        displayName: json['displayName'] as String? ?? '',
        role: json['role'] as String? ?? 'user',
        status: json['status'] as String? ?? 'active',
        createdAt: json['createdAt'] as String? ?? '',
        email: json['email'] as String? ?? '',
        lastLoginAt: json['lastLoginAt'] as String?,
      );
}

class RegistrationPolicy {
  const RegistrationPolicy({
    required this.emailRequired,
    required this.emailVerificationRequired,
    required this.identityBadgeRequired,
    this.githubLoginEnabled = false,
  });

  final bool emailRequired;
  final bool emailVerificationRequired;
  final bool identityBadgeRequired;
  final bool githubLoginEnabled;

  factory RegistrationPolicy.fromJson(Map<String, dynamic> json) =>
      RegistrationPolicy(
        // 新版本始终要求邮箱；缺少字段时也采用安全的必填默认值。
        emailRequired: json['emailRequired'] as bool? ?? true,
        emailVerificationRequired:
            json['emailVerificationRequired'] as bool? ?? false,
        identityBadgeRequired: json['identityBadgeRequired'] as bool? ?? false,
        githubLoginEnabled: json['githubLoginEnabled'] as bool? ?? false,
      );
}

class UserSession {
  const UserSession({required this.token, required this.user});

  final String token;
  final UserAccount user;

  factory UserSession.fromJson(Map<String, dynamic> json) {
    final rawUser = json['user'];
    if (rawUser is! Map) {
      throw const FormatException('用户会话缺少用户信息');
    }
    final token = json['token'] as String? ?? '';
    if (token.trim().isEmpty) {
      throw const FormatException('用户会话缺少 Token');
    }
    return UserSession(
      token: token,
      user: UserAccount.fromJson(Map<String, dynamic>.from(rawUser)),
    );
  }
}

sealed class LoginResult {
  const LoginResult();

  factory LoginResult.fromJson(Map<String, dynamic> json) {
    if (json['requiresTwoFactor'] == true) {
      return TwoFactorLoginChallenge.fromJson(json);
    }
    return AuthenticatedLogin(UserSession.fromJson(json));
  }
}

final class AuthenticatedLogin extends LoginResult {
  const AuthenticatedLogin(this.session);

  final UserSession session;
}

final class TwoFactorLoginChallenge extends LoginResult {
  const TwoFactorLoginChallenge({
    required this.challengeToken,
    required this.expiresInSeconds,
  });

  final String challengeToken;
  final int expiresInSeconds;

  factory TwoFactorLoginChallenge.fromJson(Map<String, dynamic> json) {
    final token = json['challengeToken'] as String? ?? '';
    if (token.trim().isEmpty) {
      throw const FormatException('两步验证响应缺少挑战 Token');
    }
    return TwoFactorLoginChallenge(
      challengeToken: token,
      expiresInSeconds: (json['expiresInSeconds'] as num?)?.toInt() ?? 300,
    );
  }
}

class GitHubDeviceFlow {
  const GitHubDeviceFlow({
    required this.flowId,
    required this.userCode,
    required this.verificationUri,
    required this.expiresInSeconds,
    required this.intervalSeconds,
    required this.purpose,
  });

  static final Uri trustedVerificationUri =
      Uri.parse('https://github.com/login/device');

  final String flowId;
  final String userCode;
  final String verificationUri;
  final int expiresInSeconds;
  final int intervalSeconds;
  final String purpose;

  Uri get safeVerificationUri => trustedVerificationUri;

  factory GitHubDeviceFlow.fromJson(
    Map<String, dynamic> json, {
    required String purpose,
  }) {
    final flowId = json['flowId'] as String? ?? '';
    final userCode = json['userCode'] as String? ?? '';
    if (flowId.trim().isEmpty || userCode.trim().isEmpty) {
      throw const FormatException('GitHub 授权响应不完整');
    }
    return GitHubDeviceFlow(
      flowId: flowId,
      userCode: userCode,
      verificationUri: json['verificationUri'] as String? ?? '',
      expiresInSeconds: (json['expiresInSeconds'] as num?)?.toInt() ?? 900,
      intervalSeconds:
          ((json['intervalSeconds'] as num?)?.toInt() ?? 5).clamp(1, 60),
      purpose: purpose,
    );
  }
}

enum GitHubDevicePollStatus {
  pending,
  bound,
  authenticated,
  twoFactorRequired,
}

class GitHubDevicePollResult {
  const GitHubDevicePollResult._({
    required this.status,
    this.retryAfterSeconds,
    this.githubLogin,
    this.session,
    this.challenge,
  });

  final GitHubDevicePollStatus status;
  final int? retryAfterSeconds;
  final String? githubLogin;
  final UserSession? session;
  final TwoFactorLoginChallenge? challenge;

  factory GitHubDevicePollResult.fromJson(Map<String, dynamic> json) {
    return switch (json['status']) {
      'pending' => GitHubDevicePollResult._(
          status: GitHubDevicePollStatus.pending,
          retryAfterSeconds:
              ((json['retryAfterSeconds'] as num?)?.toInt() ?? 5).clamp(1, 60),
        ),
      'bound' => GitHubDevicePollResult._(
          status: GitHubDevicePollStatus.bound,
          githubLogin: json['githubLogin'] as String? ?? '',
        ),
      'authenticated' => GitHubDevicePollResult._(
          status: GitHubDevicePollStatus.authenticated,
          session: UserSession.fromJson(json),
        ),
      'twoFactorRequired' => GitHubDevicePollResult._(
          status: GitHubDevicePollStatus.twoFactorRequired,
          challenge: TwoFactorLoginChallenge.fromJson(<String, dynamic>{
            ...json,
            'requiresTwoFactor': true,
          }),
        ),
      _ => throw const FormatException('无法识别 GitHub 授权状态'),
    };
  }
}

class AccountSecurity {
  const AccountSecurity({
    required this.githubAvailable,
    required this.githubBound,
    required this.githubLogin,
    required this.twoFactorEnabled,
    required this.recoveryCodesRemaining,
  });

  final bool githubAvailable;
  final bool githubBound;
  final String githubLogin;
  final bool twoFactorEnabled;
  final int recoveryCodesRemaining;

  factory AccountSecurity.fromJson(Map<String, dynamic> json) {
    final rawGitHub = json['github'];
    final rawTwoFactor = json['twoFactor'];
    final github = rawGitHub is Map
        ? Map<String, dynamic>.from(rawGitHub)
        : const <String, dynamic>{};
    final twoFactor = rawTwoFactor is Map
        ? Map<String, dynamic>.from(rawTwoFactor)
        : const <String, dynamic>{};
    return AccountSecurity(
      githubAvailable: github['available'] as bool? ?? false,
      githubBound: github['bound'] as bool? ?? false,
      githubLogin: github['login'] as String? ?? '',
      twoFactorEnabled: twoFactor['enabled'] as bool? ?? false,
      recoveryCodesRemaining:
          (twoFactor['recoveryCodesRemaining'] as num?)?.toInt() ?? 0,
    );
  }
}

class TwoFactorSetup {
  const TwoFactorSetup({
    required this.setupId,
    required this.secret,
    required this.otpauthUri,
    required this.expiresInSeconds,
  });

  final String setupId;
  final String secret;
  final String otpauthUri;
  final int expiresInSeconds;

  factory TwoFactorSetup.fromJson(Map<String, dynamic> json) {
    final setupId = json['setupId'] as String? ?? '';
    final secret = json['secret'] as String? ?? '';
    final otpauthUri = json['otpauthUri'] as String? ?? '';
    if (setupId.trim().isEmpty || secret.trim().isEmpty || otpauthUri.isEmpty) {
      throw const FormatException('两步验证设置响应不完整');
    }
    return TwoFactorSetup(
      setupId: setupId,
      secret: secret,
      otpauthUri: otpauthUri,
      expiresInSeconds: (json['expiresInSeconds'] as num?)?.toInt() ?? 600,
    );
  }
}

class RecoveryCodes {
  const RecoveryCodes(this.values);

  final List<String> values;

  factory RecoveryCodes.fromJson(Map<String, dynamic> json) {
    final values = (json['recoveryCodes'] as List? ?? const <dynamic>[])
        .whereType<String>()
        .where((value) => value.trim().isNotEmpty)
        .toList(growable: false);
    if (values.isEmpty) {
      throw const FormatException('服务器未返回恢复码');
    }
    return RecoveryCodes(values);
  }
}
