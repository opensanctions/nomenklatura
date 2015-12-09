
nomenklatura.directive('nkPager', ['$timeout', function ($timeout) {
	return {
		restrict: 'E',
		scope: {
			'response': '=',
			'load': '&load'
		},
		templateUrl: '/static/templates/pager.html',
		link: function (scope, element, attrs, model) {
			scope.showPager = false;
			scope.$watch('response', function(e) {
				if (!scope.response.count) {
					return;
				}
				var pages = [],
					current = (scope.response.offset / scope.response.limit) + 1,
					num = Math.ceil(scope.response.count / scope.response.limit),
					range = 3,
					low = current - range,
					high = current + range;

				if (low < 1) {
					low = 1;
					high = Math.min((2*range)+1, num);
				}
				if (high > num) {
					high = num;
					low = Math.max(1, num - (2*range)+1);
				}

				for (var page = low; page <= high; page++) {
					var offset = (page-1) * scope.response.limit,
						url = scope.response.format.replace('LIMIT', scope.response.limit).replace('OFFSET', offset);
					pages.push({
						page: page,
						current: page==current,
						url: url
					});
				}
				scope.showPager = scope.response.count > scope.response.limit;
				scope.pages = pages;
			});
		}
	};
}]);
