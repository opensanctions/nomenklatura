
nomenklatura.directive('nkAuthz', ['$timeout', 'session', function ($timeout, session) {
	return {
		restrict: 'AE',
		scope: {
			'dataset': '=',
			'operation': '@op',
		},
		link: function (scope, element, attrs, model) {
			element.addClass('hidden');
			scope.$watch('dataset', function(n, o, dataset) {
				if (scope.dataset && scope.dataset.name) {
					session.authz(scope.dataset.name).then(function(res) {
						var perms = res.data[scope.dataset.name];
						if (perms[scope.operation]) {
							element.removeClass('hidden');
						}
					});
				}
			});
		}
	};
}]);
