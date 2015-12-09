
nomenklatura.controller('DocsCtrl', ['$scope', '$routeParams', 
		function($scope, $routeParams) {
	$scope.template = '/static/templates/docs/' + $routeParams.page + '.html';

	$scope.active = function(path) {
		return $routeParams.page == path ? 'active' : '';
	};
}]);
