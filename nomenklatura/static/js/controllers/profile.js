
nomenklatura.controller('ProfileCtrl', ['$scope', '$location', '$modalInstance', 'session', 
		function($scope, $location, $modalInstance, session) {
	$scope.session = {logged_in: false};

	session.get(function(data) {
		$scope.session = data;
	});

	$scope.cancel = function() {
		$modalInstance.dismiss('cancel');
	};
	
}]);
